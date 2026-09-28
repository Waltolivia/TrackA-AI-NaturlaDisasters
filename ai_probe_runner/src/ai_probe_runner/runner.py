from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .providers import make_provider
from .questions import build_questions, normalize_trigger

SCHEMA_VERSION = "1.2"
REQUIRED_TARGET_FIELDS = {
    "target_id",
    "provider",
    "model",
    "interface",
    "browsing",
    "enabled",
}
KNOWN_PROVIDERS = {"anthropic", "google", "mock", "openai"}
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


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
    resume: bool = False,
) -> dict[str, Any]:
    raw_trigger = dict(trigger)
    trigger = normalize_trigger(raw_trigger)
    questions, bank_paths = build_questions(trigger, bank_dir)
    targets = load_targets(targets_path)
    cycle_id = str(
        cycle_id or trigger.get("cycle_id") or trigger.get("message_id") or uuid.uuid4()
    )
    if not CYCLE_ID_PATTERN.fullmatch(cycle_id):
        raise ValueError(
            "cycle_id must start with a letter or number and contain only "
            "letters, numbers, periods, underscores, or hyphens"
        )

    run_started_at = utc_now()
    cycle_dir, existing = _resolve_cycle_dir(
        output_dir, cycle_id, run_started_at, resume
    )
    raw_dir = cycle_dir / "raw"
    records_path = cycle_dir / "probes.jsonl"
    question_hashes = {
        str(path.relative_to(bank_dir)): file_sha256(path) for path in bank_paths
    }
    input_hash = _json_sha256(raw_trigger)
    normalized_hash = _json_sha256(trigger)
    targets_hash = file_sha256(targets_path)

    manifest_path = cycle_dir / "manifest.json"
    if existing and not manifest_path.exists():
        has_probe_data = records_path.exists() or (
            raw_dir.exists() and any(raw_dir.iterdir())
        )
        if has_probe_data:
            raise ValueError(
                f"Cycle {cycle_id!r} has probe data but no manifest; "
                "manual review required"
            )
        existing = False

    if existing:
        manifest = _load_json(manifest_path)
        _verify_resume(
            manifest=manifest,
            input_hash=input_hash,
            normalized_hash=normalized_hash,
            question_hashes=question_hashes,
            targets_hash=targets_hash,
            expected_count=len(questions) * len(targets),
        )
        manifest["schema_version"] = SCHEMA_VERSION
        manifest["cycle_completed_at"] = None
        manifest["cycle_last_resumed_at"] = run_started_at
        manifest["run_attempt_count"] = int(manifest.get("run_attempt_count", 1)) + 1
        manifest["last_git_commit"] = git_commit()
        _write_json(cycle_dir / "trigger.raw.json", raw_trigger)
        _write_json(cycle_dir / "trigger.json", trigger)
        _write_json(cycle_dir / "questions.json", questions)
    else:
        cycle_dir.mkdir(parents=True, exist_ok=True)
        current_commit = git_commit()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "cycle_id": cycle_id,
            "cycle_started_at": run_started_at,
            "cycle_last_resumed_at": None,
            "cycle_completed_at": None,
            "run_attempt_count": 1,
            "trigger_input_sha256": input_hash,
            "trigger_sha256": normalized_hash,
            "question_bank_sha256": question_hashes,
            "targets_sha256": targets_hash,
            "git_commit": current_commit,
            "last_git_commit": current_commit,
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "expected_probe_count": len(questions) * len(targets),
            "completed_probe_count": 0,
            "failed_probe_count": 0,
            "pending_probe_count": len(questions) * len(targets),
            "cycle_status": "running",
            "hazard_family": trigger["hazard_family"],
            "ground_truth_message_id": trigger.get("message_id"),
            "ground_truth_event_id": trigger.get("event_id"),
            "ground_truth_trigger": trigger.get("trigger") or trigger.get("action"),
            "ground_truth_timestamp": trigger.get("timestamp"),
            "ground_truth_source": trigger["source"],
            "ground_truth_source_id": trigger["source_id"],
        }
        _write_json(cycle_dir / "trigger.raw.json", raw_trigger)
        _write_json(cycle_dir / "trigger.json", trigger)
        _write_json(cycle_dir / "questions.json", questions)

    raw_dir.mkdir(parents=True, exist_ok=True)
    records = _load_records(records_path)
    latest = _latest_records(records)
    attempts = _attempt_counts(records)
    _refresh_manifest_counts(manifest, latest)
    _write_json(manifest_path, manifest)

    for target in targets:
        remaining = [
            question
            for question in questions
            if latest.get(_probe_key(target, question), {}).get("status") != "success"
        ]
        if not remaining:
            continue

        try:
            provider = make_provider(target["provider"])
            provider_error: Exception | None = None
        except Exception as exc:
            provider = None
            provider_error = exc

        for question in remaining:
            probe_key = _probe_key(target, question)
            attempt = attempts.get(probe_key, 0) + 1
            probe_id = str(uuid.uuid4())
            started_clock = time.monotonic()
            record: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "cycle_id": cycle_id,
                "probe_id": probe_id,
                "probe_key": probe_key,
                "attempt": attempt,
                "question": question,
                "target": target,
                "request_started_at": utc_now(),
                "trigger_reference": {
                    "message_id": trigger.get("message_id"),
                    "event_id": trigger.get("event_id"),
                    "trigger": trigger.get("trigger") or trigger.get("action"),
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
                record.update(
                    {
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
                    }
                )
            except Exception as exc:
                record.update(
                    {
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
                    }
                )

            with records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
            latest[probe_key] = record
            attempts[probe_key] = attempt
            _refresh_manifest_counts(manifest, latest)
            _write_json(manifest_path, manifest)
            if delay_seconds:
                time.sleep(delay_seconds)

    manifest["cycle_completed_at"] = utc_now()
    _refresh_manifest_counts(manifest, latest)
    manifest["cycle_status"] = (
        "complete" if manifest["failed_probe_count"] == 0 else "partial"
    )
    _write_json(manifest_path, manifest)
    return {"cycle_dir": str(cycle_dir), **manifest}


def load_targets(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Target configuration must be a JSON list: {path}")

    ids: list[str] = []
    enabled: list[dict[str, Any]] = []
    for index, target in enumerate(data):
        if not isinstance(target, dict):
            raise ValueError(f"Target #{index + 1} must be a JSON object")
        missing = sorted(REQUIRED_TARGET_FIELDS - target.keys())
        if missing:
            raise ValueError(
                f"Target #{index + 1} is missing fields: {', '.join(missing)}"
            )
        if target["provider"] not in KNOWN_PROVIDERS:
            raise ValueError(f"Unknown provider in target {target['target_id']!r}")
        if not isinstance(target["browsing"], bool):
            raise ValueError(f"Target {target['target_id']!r} browsing must be boolean")
        if not isinstance(target["enabled"], bool):
            raise ValueError(f"Target {target['target_id']!r} enabled must be boolean")
        ids.append(str(target["target_id"]))
        if target["enabled"]:
            enabled.append(target)

    if len(ids) != len(set(ids)):
        raise ValueError("Target IDs must be unique")
    if not enabled:
        raise ValueError("Target configuration has no enabled targets")
    return enabled


def _resolve_cycle_dir(
    output_dir: Path, cycle_id: str, started_at: str, resume: bool
) -> tuple[Path, bool]:
    matches = sorted(path for path in output_dir.glob(f"*/{cycle_id}") if path.is_dir())
    if len(matches) > 1:
        raise ValueError(f"Multiple cycle directories found for {cycle_id!r}")
    if matches:
        if not resume:
            raise FileExistsError(
                f"Cycle {cycle_id!r} already exists; pass --resume to continue it"
            )
        return matches[0], True
    return output_dir / started_at[:10] / cycle_id, False


def _verify_resume(
    *,
    manifest: dict[str, Any],
    input_hash: str,
    normalized_hash: str,
    question_hashes: dict[str, str],
    targets_hash: str,
    expected_count: int,
) -> None:
    expected = {
        "trigger_input_sha256": input_hash,
        "trigger_sha256": normalized_hash,
        "question_bank_sha256": question_hashes,
        "targets_sha256": targets_hash,
        "expected_probe_count": expected_count,
    }
    mismatched = [key for key, value in expected.items() if manifest.get(key) != value]
    if mismatched:
        raise ValueError(
            "Cannot resume because research inputs changed: " + ", ".join(mismatched)
        )


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in {path} at line {line_number}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise ValueError(f"Probe record at {path}:{line_number} is not an object")
        records.append(record)
    return records


def _probe_key(target: dict[str, Any], question: dict[str, Any]) -> str:
    return f"{target['target_id']}::{question['question_id']}"


def _record_key(record: dict[str, Any]) -> str:
    if record.get("probe_key"):
        return str(record["probe_key"])
    return _probe_key(record["target"], record["question"])


def _latest_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[_record_key(record)] = record
    return latest


def _attempt_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    attempts: dict[str, int] = {}
    for record in records:
        key = _record_key(record)
        attempts[key] = max(attempts.get(key, 0), int(record.get("attempt", 1)))
    return attempts


def _refresh_manifest_counts(
    manifest: dict[str, Any], latest: dict[str, dict[str, Any]]
) -> None:
    manifest["completed_probe_count"] = sum(
        record.get("status") == "success" for record in latest.values()
    )
    manifest["failed_probe_count"] = sum(
        record.get("status") == "error" for record in latest.values()
    )
    manifest["pending_probe_count"] = max(
        0,
        int(manifest["expected_probe_count"])
        - manifest["completed_probe_count"]
        - manifest["failed_probe_count"],
    )


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected one JSON object in {path}")
    return value


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
