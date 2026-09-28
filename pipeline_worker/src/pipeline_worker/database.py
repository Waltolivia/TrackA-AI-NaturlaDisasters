from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    trigger_sha256 TEXT NOT NULL UNIQUE,
    trigger_path TEXT NOT NULL,
    event_id TEXT,
    trigger_type TEXT,
    schema_version INTEGER,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    lease_until TEXT,
    discovered_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    cycle_id TEXT NOT NULL,
    cycle_dir TEXT,
    last_exit_code INTEGER,
    last_stdout TEXT,
    last_stderr TEXT,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_ready
ON jobs(status, available_at, discovered_at);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (
        (value or utc_now()).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


class JobDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def add_job(
        self,
        *,
        job_id: str,
        trigger_sha256: str,
        trigger_path: Path,
        event_id: str | None,
        trigger_type: str | None,
        schema_version: int | None,
        status: str = "PENDING",
        error: str | None = None,
    ) -> bool:
        now = timestamp()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT trigger_sha256 FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if existing:
                if existing["trigger_sha256"] != trigger_sha256:
                    raise ValueError(
                        f"Trigger ID collision for {job_id}: payload hashes differ"
                    )
                return False
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, trigger_sha256, trigger_path, event_id, trigger_type,
                    schema_version, status, available_at, discovered_at, cycle_id,
                    last_error, completed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    trigger_sha256,
                    str(trigger_path),
                    event_id,
                    trigger_type,
                    schema_version,
                    status,
                    now,
                    now,
                    job_id,
                    error,
                    now if status in {"SKIPPED", "INVALID"} else None,
                ),
            )
            return True

    def update_trigger_path(self, job_id: str, path: Path) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET trigger_path=? WHERE job_id=?",
                (str(path), job_id),
            )

    def claim_next(
        self, max_attempts: int, lease_seconds: int
    ) -> dict[str, Any] | None:
        now_dt = utc_now()
        now = timestamp(now_dt)
        lease_until = timestamp(now_dt + timedelta(seconds=lease_seconds))
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE jobs
                SET status=CASE WHEN attempt_count>=? THEN 'DEAD' ELSE 'RETRY' END,
                    available_at=?, lease_until=NULL,
                    last_error=COALESCE(last_error, 'Worker lease expired')
                WHERE status='RUNNING' AND lease_until IS NOT NULL AND lease_until<=?
                """,
                (max_attempts, now, now),
            )
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status IN ('PENDING','RETRY')
                  AND available_at<=?
                  AND attempt_count<?
                ORDER BY discovered_at, job_id
                LIMIT 1
                """,
                (now, max_attempts),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE jobs
                SET status='RUNNING', attempt_count=attempt_count+1,
                    started_at=?, lease_until=?
                WHERE job_id=?
                """,
                (now, lease_until, row["job_id"]),
            )
            claimed = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            return dict(claimed)

    def succeed(
        self,
        job_id: str,
        *,
        cycle_dir: str,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status='SUCCEEDED', completed_at=?, lease_until=NULL,
                    cycle_dir=?, last_exit_code=?, last_stdout=?, last_stderr=?,
                    last_error=NULL
                WHERE job_id=?
                """,
                (
                    timestamp(),
                    cycle_dir,
                    exit_code,
                    stdout,
                    stderr,
                    job_id,
                ),
            )

    def fail(
        self,
        job_id: str,
        *,
        max_attempts: int,
        retry_base_seconds: float,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        error: str,
    ) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            attempts = int(row["attempt_count"])
            final = attempts >= max_attempts
            status = "DEAD" if final else "RETRY"
            delay = retry_base_seconds * (2 ** max(0, attempts - 1))
            available_at = timestamp(utc_now() + timedelta(seconds=delay))
            connection.execute(
                """
                UPDATE jobs SET status=?, available_at=?, lease_until=NULL,
                    completed_at=?, last_exit_code=?, last_stdout=?, last_stderr=?,
                    last_error=?
                WHERE job_id=?
                """,
                (
                    status,
                    available_at,
                    timestamp() if final else None,
                    exit_code,
                    stdout,
                    stderr,
                    error,
                    job_id,
                ),
            )
            return status

    def retry(self, job_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status='PENDING', attempt_count=0,
                    available_at=?, lease_until=NULL, completed_at=NULL,
                    last_error=NULL
                WHERE job_id=? AND status IN ('DEAD','RETRY')
                """,
                (timestamp(), job_id),
            )
            return cursor.rowcount == 1

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            return dict(row) if row else None

    def summary(self, limit: int = 20) -> dict[str, Any]:
        with self.connect() as connection:
            counts = {
                row["status"]: row["count"]
                for row in connection.execute(
                    "SELECT status, count(*) count FROM jobs GROUP BY status"
                )
            }
            rows = connection.execute(
                """
                SELECT job_id,event_id,trigger_type,status,attempt_count,
                       discovered_at,completed_at,cycle_dir,last_error
                FROM jobs ORDER BY discovered_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return {"counts": counts, "recent_jobs": [dict(row) for row in rows]}
