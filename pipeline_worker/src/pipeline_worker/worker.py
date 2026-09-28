from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_probe_runner.questions import PROBE_TRIGGER_TYPES, normalize_trigger

from .config import WorkerConfig
from .database import JobDatabase

log = logging.getLogger("pipeline-worker")
NON_PROBE_ACTIONS = {
    "COLLECTION_COMPLETE",
    "EVENT_ENDED",
    "ROUTINE_UPDATE",
    "UPDATE",
}


@dataclass(frozen=True)
class InvocationResult:
    success: bool
    exit_code: int | None
    stdout: str
    stderr: str
    summary: dict[str, Any] | None
    error: str | None


class PipelineWorker:
    def __init__(self, config: WorkerConfig):
        self.config = config.resolved()
        self.database = JobDatabase(self.config.state_db)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        if self.config.queue_layout == "v5":
            for state in ("pending", "processing", "completed", "failed"):
                (self.config.outbox / state).mkdir(parents=True, exist_ok=True)
        else:
            self.config.outbox.mkdir(parents=True, exist_ok=True)

    def discover(self) -> dict[str, int]:
        counts = {"discovered": 0, "duplicate": 0, "skipped": 0, "invalid": 0}
        for path in self._queue_files():
            outcome = self._discover_file(path)
            counts[outcome] += 1
        return counts

    def run_once(self, max_jobs: int | None = None) -> dict[str, Any]:
        discovery = self.discover()
        processed = succeeded = failed = 0
        while max_jobs is None or processed < max_jobs:
            job = self.database.claim_next(
                self.config.max_attempts, self.config.lease_seconds
            )
            if job is None:
                break
            processed += 1
            if self._process_job(job):
                succeeded += 1
            else:
                failed += 1
        return {
            "discovery": discovery,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "state": self.database.summary(),
        }

    def run_forever(self) -> None:
        log.info(
            "worker started outbox=%s targets=%s output=%s",
            self.config.outbox,
            self.config.targets,
            self.config.output_dir,
        )
        try:
            while True:
                result = self.run_once(max_jobs=1)
                if result["processed"] == 0:
                    time.sleep(self.config.poll_seconds)
        except KeyboardInterrupt:
            log.info("worker stopped")

    def _queue_files(self) -> list[Path]:
        if self.config.queue_layout == "v5":
            pending = list((self.config.outbox / "pending").glob("*.json"))
            processing = list((self.config.outbox / "processing").glob("*.json"))
            return sorted(pending + processing)
        return sorted(self.config.outbox.glob("*.json"))

    def _discover_file(self, path: Path) -> str:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            log.warning("cannot read trigger %s: %s", path, exc)
            return "invalid"
        digest = hashlib.sha256(raw).hexdigest()

        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("trigger JSON must contain one object")
        except (json.JSONDecodeError, ValueError) as exc:
            job_id = f"INVALID-{digest[:24]}"
            inserted = self.database.add_job(
                job_id=job_id,
                trigger_sha256=digest,
                trigger_path=path,
                event_id=None,
                trigger_type=None,
                schema_version=None,
                status="INVALID",
                error=str(exc),
            )
            if inserted:
                moved = self._finish_queue_file(path, "failed")
                if moved != path:
                    self.database.update_trigger_path(job_id, moved)
                return "invalid"
            self._ack_duplicate(job_id, path)
            return "duplicate"

        job_id = self._job_id(payload, digest)
        trigger_type = payload.get("action") or payload.get("trigger")
        event_id = payload.get("event_id")
        schema_version = payload.get("schema_version")
        try:
            schema_number = int(schema_version) if schema_version is not None else None
        except (TypeError, ValueError):
            schema_number = None

        if trigger_type in NON_PROBE_ACTIONS:
            inserted = self.database.add_job(
                job_id=job_id,
                trigger_sha256=digest,
                trigger_path=path,
                event_id=str(event_id) if event_id else None,
                trigger_type=str(trigger_type),
                schema_version=schema_number,
                status="SKIPPED",
                error=f"Non-probe action: {trigger_type}",
            )
            if inserted:
                moved = self._finish_queue_file(path, "completed")
                if moved != path:
                    self.database.update_trigger_path(job_id, moved)
                return "skipped"
            self._ack_duplicate(job_id, path)
            return "duplicate"

        try:
            normalized = normalize_trigger(payload)
        except ValueError as exc:
            inserted = self.database.add_job(
                job_id=job_id,
                trigger_sha256=digest,
                trigger_path=path,
                event_id=str(event_id) if event_id else None,
                trigger_type=str(trigger_type) if trigger_type else None,
                schema_version=schema_number,
                status="SKIPPED",
                error=str(exc),
            )
            if inserted:
                moved = self._finish_queue_file(path, "completed")
                if moved != path:
                    self.database.update_trigger_path(job_id, moved)
                return "skipped"
            self._ack_duplicate(job_id, path)
            return "duplicate"

        normalized_type = normalized.get("trigger") or normalized.get("action")
        if normalized_type not in PROBE_TRIGGER_TYPES:
            raise ValueError(f"Unexpected normalized trigger type: {normalized_type}")
        area = str(normalized.get("area") or "").strip().lower()
        if area.startswith("coordinates="):
            inserted = self.database.add_job(
                job_id=job_id,
                trigger_sha256=digest,
                trigger_path=path,
                event_id=str(normalized.get("event_id") or "") or None,
                trigger_type=str(normalized_type),
                schema_version=schema_number,
                status="SKIPPED",
                error="Coordinate-only location requires reviewed location enrichment",
            )
            if inserted:
                moved = self._finish_queue_file(path, "completed")
                if moved != path:
                    self.database.update_trigger_path(job_id, moved)
                return "skipped"
            self._ack_duplicate(job_id, path)
            return "duplicate"
        inserted = self.database.add_job(
            job_id=job_id,
            trigger_sha256=digest,
            trigger_path=path,
            event_id=str(normalized.get("event_id") or "") or None,
            trigger_type=str(normalized_type),
            schema_version=schema_number,
        )
        if not inserted:
            self._ack_duplicate(job_id, path)
        return "discovered" if inserted else "duplicate"

    def _job_id(self, payload: dict[str, Any], digest: str) -> str:
        message_id = payload.get("message_id")
        if isinstance(message_id, str) and message_id:
            candidate = message_id.strip()
            if (
                len(candidate) <= 128
                and candidate[0].isalnum()
                and all(char.isalnum() or char in "._-" for char in candidate)
            ):
                return candidate
        return f"TRG-{digest[:24]}"

    def _process_job(self, job: dict[str, Any]) -> bool:
        job_id = str(job["job_id"])
        path = Path(str(job["trigger_path"]))
        try:
            claimed_path = self._claim_queue_file(path)
            if claimed_path != path:
                self.database.update_trigger_path(job_id, claimed_path)
                path = claimed_path
            if not path.is_file():
                raise FileNotFoundError(f"Claimed trigger file does not exist: {path}")
            result = self._invoke_ai(job_id, path)
        except Exception as exc:
            result = InvocationResult(
                success=False,
                exit_code=None,
                stdout="",
                stderr="",
                summary=None,
                error=f"{type(exc).__name__}: {exc}",
            )

        if result.success and result.summary is not None:
            completed_path = self._finish_queue_file(path, "completed")
            if completed_path != path:
                self.database.update_trigger_path(job_id, completed_path)
            self.database.succeed(
                job_id,
                cycle_dir=str(result.summary["cycle_dir"]),
                exit_code=result.exit_code or 0,
                stdout=_bounded(result.stdout),
                stderr=_bounded(result.stderr),
            )
            log.info(
                "job succeeded job_id=%s cycle=%s",
                job_id,
                result.summary["cycle_dir"],
            )
            return True

        status = self.database.fail(
            job_id,
            max_attempts=self.config.max_attempts,
            retry_base_seconds=self.config.retry_base_seconds,
            exit_code=result.exit_code,
            stdout=_bounded(result.stdout),
            stderr=_bounded(result.stderr),
            error=result.error or "AI probe runner failed",
        )
        if status == "DEAD":
            failed_path = self._finish_queue_file(path, "failed")
            if failed_path != path:
                self.database.update_trigger_path(job_id, failed_path)
        log.warning(
            "job failed job_id=%s status=%s error=%s",
            job_id,
            status,
            result.error,
        )
        return False

    def _invoke_ai(self, job_id: str, trigger_path: Path) -> InvocationResult:
        command = [
            sys.executable,
            "-m",
            "ai_probe_runner.cli",
            "--trigger",
            str(trigger_path),
            "--targets",
            str(self.config.targets),
            "--question-bank-dir",
            str(self.config.question_bank_dir),
            "--output",
            str(self.config.output_dir),
            "--cycle-id",
            job_id,
            "--delay-seconds",
            str(self.config.probe_delay_seconds),
            "--resume",
            "--fail-on-probe-error",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.config.ai_project,
                capture_output=True,
                text=True,
                timeout=self.config.job_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return InvocationResult(
                success=False,
                exit_code=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                summary=None,
                error=(
                    f"AI probe cycle exceeded {self.config.job_timeout_seconds} seconds"
                ),
            )

        try:
            summary = json.loads(completed.stdout)
            if not isinstance(summary, dict):
                raise ValueError("summary is not a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            return InvocationResult(
                success=False,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                summary=None,
                error=f"Could not parse AI runner summary: {exc}",
            )

        expected = int(summary.get("expected_probe_count", -1))
        completed_count = int(summary.get("completed_probe_count", -1))
        failed_count = int(summary.get("failed_probe_count", -1))
        success = (
            completed.returncode == 0
            and expected >= 0
            and completed_count == expected
            and failed_count == 0
        )
        error = (
            None
            if success
            else (
                f"AI runner exit={completed.returncode}, expected={expected}, "
                f"completed={completed_count}, failed={failed_count}"
            )
        )
        return InvocationResult(
            success=success,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            summary=summary,
            error=error,
        )

    def _claim_queue_file(self, path: Path) -> Path:
        if self.config.queue_layout != "v5" or path.parent.name != "pending":
            return path
        target = self.config.outbox / "processing" / path.name
        if target.exists():
            raise FileExistsError(f"Queue claim target already exists: {target}")
        return path.replace(target)

    def _ack_duplicate(self, job_id: str, path: Path) -> None:
        if self.config.queue_layout != "v5" or path.parent.name not in {
            "pending",
            "processing",
        }:
            return
        job = self.database.get(job_id)
        if (
            path.parent.name == "processing"
            and job
            and job["status"]
            not in {
                "DEAD",
                "INVALID",
                "SKIPPED",
                "SUCCEEDED",
            }
        ):
            return
        state = (
            "failed" if job and job["status"] in {"DEAD", "INVALID"} else "completed"
        )
        self._finish_queue_file(path, state)

    def _finish_queue_file(self, path: Path, state: str) -> Path:
        if self.config.queue_layout != "v5" or path.parent.name not in {
            "pending",
            "processing",
        }:
            return path
        destination = self.config.outbox / state
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / path.name
        if target.exists():
            target = destination / f"{path.stem}.{time.time_ns()}{path.suffix}"
        return Path(shutil.move(str(path), str(target)))


def _bounded(value: str, limit: int = 100_000) -> str:
    return value if len(value) <= limit else value[-limit:]
