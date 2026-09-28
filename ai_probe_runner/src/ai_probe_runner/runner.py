from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .providers import make_provider
from .questions import build_questions

SCHEMA_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_cycle(
    *,
    trigger: dict[str, Any],
    targets_path: Path,
    bank_dir: Path,
    output_dir: Path,
    cycle_id: str | None = None,
    delay_seconds: float = 0.0,
) -> dict[str, Any]:
    questions, bank_paths = build_questions(trigger, bank_dir)
    targets_data = json.loads(targets_path.read_text(encoding="utf-8"))
    targets = [target for target in targets_data if target.get("enabled", True)]
    cycle_id = cycle_id or trigger.get("cycle_id") or str(uuid.uuid4())
    cycle_started_at = utc_now()
    cycle_dir = output_dir / cycle_started_at[:10] / str(cycle_id)
    raw_dir = cycle_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": cycle_id,
        "cycle_started_at": cycle_started_at,
        "cycle_completed_at": None,
        "trigger_sha256": _json_sha256(trigger),
        "question_bank_sha256": {
            str(path.relative_to(bank_dir)): file_sha256(path)
            for path in bank_paths
        },
        "targets_sha256": file_sha256(targets_path),
        "git_commit": git_commit(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "expected_probe_count": len(questions) * len(targets),
        "completed_probe_count": 0,
        "failed_probe_count": 0,
        "hazard_family": trigger["hazard_family"],
        "ground_truth_source": trigger["source"],
        "ground_truth_source_id": trigger["source_id"],
    }
    _write_json(cycle_dir / "manifest.json", manifest)
    _write_json(cycle_dir / "trigger.json", trigger)
    _write_json(cycle_dir / "questions.json", questions)

    records_path = cycle_dir / "probes.jsonl"
    for target in targets:
        try:
            provider = make_provider(target["provider"])
            provider_error: Exception | None = None
        except Exception as exc:
            provider = None
            provider_error = exc

        for question in questions:
            probe_id = str(uuid.uuid4())
            started_clock = time.monotonic()
            record: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "cycle_id": cycle_id,
                "probe_id": probe_id,
                "question": question,
                "target": target,
                "request_started_at": utc_now(),
                "trigger_reference": {
                    "source": trigger["source"],
                    "source_id": trigger["source_id"],
                    "version_hash": trigger.get("version_hash"),
                    "hazard_family": trigger["hazard_family"],
                },
            }
            try:
                if provider_error:
                    raise provider_error
                assert provider is not None
                result = provider.ask(
                    prompt=question["prompt"],
                    model=target["model"],
                    browsing=target.get("browsing", False),
                )
                raw_name = f"{probe_id}.json"
                _write_json(raw_dir / raw_name, result.raw)
                record.update({
                    "status": "success",
                    "response_completed_at": utc_now(),
                    "latency_ms": round((time.monotonic() - started_clock) * 1000),
                    "response_text": result.text,
                    "provider_response_id": result.response_id,
                    "resolved_model": result.resolved_model,
                    "citations": result.citations,
                    "usage": result.usage,
                    "raw_response_path": f"raw/{raw_name}",
                    "error": None,
                })
                manifest["completed_probe_count"] += 1
            except Exception as exc:
                record.update({
                    "status": "error",
                    "response_completed_at": utc_now(),
                    "latency_ms": round((time.monotonic() - started_clock) * 1000),
                    "response_text": None,
                    "provider_response_id": None,
                    "resolved_model": None,
                    "citations": [],
                    "usage": None,
                    "raw_response_path": None,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                })
                manifest["failed_probe_count"] += 1

            with records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
            _write_json(cycle_dir / "manifest.json", manifest)
            if delay_seconds:
                time.sleep(delay_seconds)

    manifest["cycle_completed_at"] = utc_now()
    _write_json(cycle_dir / "manifest.json", manifest)
    return {"cycle_dir": str(cycle_dir), **manifest}


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
