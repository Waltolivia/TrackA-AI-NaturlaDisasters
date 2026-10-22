from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .providers import make_provider
from .questions import build_questions, normalize_trigger

SCHEMA_VERSION = "1.3"
HUMAN_OUTPUT_SCHEMA_VERSION = "1.1"
REQUIRED_TARGET_FIELDS = {
    "target_id",
    "provider",
    "model",
    "interface",
    "browsing",
    "max_output_tokens",
    "enabled",
}
KNOWN_PROVIDERS = {"anthropic", "google", "mock", "openai"}
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}
log = logging.getLogger("ai-probe-runner")


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
        output_dir, cycle_id, run_started_at, trigger, resume
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
        manifest.setdefault(
            "study_conditions",
            sorted(
                {
                    str(target.get("study_id") or "unspecified")
                    for target in targets
                }
            ),
        )
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
            "study_conditions": sorted(
                {
                    str(target.get("study_id") or "unspecified")
                    for target in targets
                }
            ),
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
    _write_readable_outputs(cycle_dir, manifest, trigger, latest)

    total = len(questions) * len(targets)
    log.info(
        "cycle started id=%s event=%s action=%s hazard=%s area=%s",
        cycle_id,
        trigger.get("event_id") or "unassigned-event",
        trigger.get("trigger") or trigger.get("action") or "manual",
        trigger["hazard_family"],
        trigger["area"],
    )
    log.info(
        "results directory=%s completed=%s/%s",
        cycle_dir,
        manifest["completed_probe_count"],
        total,
    )
    remaining_total = total - manifest["completed_probe_count"]
    attempt_ordinal = 0

    for target in targets:
        remaining = [
            question
            for question in questions
            if latest.get(_probe_key(target, question), {}).get("status") != "success"
        ]
        if not remaining:
            log.info(
                "target already complete provider=%s model=%s",
                target["provider"],
                target["model"],
            )
            continue

        log.info(
            "target started provider=%s model=%s questions=%s",
            target["provider"],
            target["model"],
            len(remaining),
        )

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
            attempt_ordinal += 1
            log.info(
                "probe attempt %s/%s started provider=%s question=%s",
                attempt_ordinal,
                remaining_total,
                target["provider"],
                question["question_id"],
            )
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
                ask_kwargs = dict(
                    prompt=question["prompt"],
                    model=target["model"],
                    browsing=target.get("browsing", False),
                    max_output_tokens=target["max_output_tokens"],
                )
                if target.get("effort") is not None:
                    ask_kwargs["effort"] = target["effort"]
                if target.get("max_search_uses") is not None:
                    ask_kwargs["max_search_uses"] = target["max_search_uses"]
                result = provider.ask(**ask_kwargs)
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
                        "search_requested": bool(target.get("browsing")),
                        "search_count": result.search_count,
                        "search_used": result.search_count > 0,
                        "raw_response_path": f"raw/{raw_name}",
                        "error": None,
                    }
                )
                log.info(
                    "probe attempt %s/%s completed provider=%s question=%s latency_ms=%s",
                    attempt_ordinal,
                    remaining_total,
                    target["provider"],
                    question["question_id"],
                    record["latency_ms"],
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
                        "search_requested": bool(target.get("browsing")),
                        "search_count": None,
                        "search_used": None,
                        "raw_response_path": None,
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                )
                log.error(
                    "probe attempt %s/%s failed provider=%s question=%s error=%s: %s",
                    attempt_ordinal,
                    remaining_total,
                    target["provider"],
                    question["question_id"],
                    type(exc).__name__,
                    exc,
                )

            with records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
            latest[probe_key] = record
            attempts[probe_key] = attempt
            _refresh_manifest_counts(manifest, latest)
            _write_json(manifest_path, manifest)
            _write_readable_outputs(cycle_dir, manifest, trigger, latest)
            if delay_seconds:
                time.sleep(delay_seconds)

    manifest["cycle_completed_at"] = utc_now()
    _refresh_manifest_counts(manifest, latest)
    manifest["cycle_status"] = (
        "complete" if manifest["failed_probe_count"] == 0 else "partial"
    )
    _write_json(manifest_path, manifest)
    _write_readable_outputs(cycle_dir, manifest, trigger, latest)
    _write_latest_convenience_files(cycle_dir, manifest)
    log.info(
        "cycle finished id=%s status=%s completed=%s failed=%s",
        cycle_id,
        manifest["cycle_status"],
        manifest["completed_probe_count"],
        manifest["failed_probe_count"],
    )
    log.info("human-readable results=%s", cycle_dir / "AI_RESULTS.md")
    return {
        "cycle_dir": str(cycle_dir),
        "readable_results": str(cycle_dir / "AI_RESULTS.md"),
        "compact_results": str(cycle_dir / "responses.json"),
        **manifest,
    }


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
        if (
            not isinstance(target["max_output_tokens"], int)
            or isinstance(target["max_output_tokens"], bool)
            or target["max_output_tokens"] < 1
        ):
            raise ValueError(
                f"Target {target['target_id']!r} max_output_tokens "
                "must be a positive integer"
            )
        effort = target.get("effort")
        if effort is not None:
            if target["provider"] != "anthropic":
                raise ValueError(
                    f"Target {target['target_id']!r} effort is supported only "
                    "for Anthropic targets"
                )
            if effort not in EFFORT_LEVELS:
                allowed = ", ".join(sorted(EFFORT_LEVELS))
                raise ValueError(
                    f"Target {target['target_id']!r} effort must be one of: {allowed}"
                )
        max_search_uses = target.get("max_search_uses")
        if max_search_uses is not None:
            if not target["browsing"]:
                raise ValueError(
                    f"Target {target['target_id']!r} max_search_uses requires browsing"
                )
            if target["provider"] not in {"anthropic", "openai"}:
                raise ValueError(
                    f"Target {target['target_id']!r} provider does not expose "
                    "a supported max_search_uses control"
                )
            if (
                not isinstance(max_search_uses, int)
                or isinstance(max_search_uses, bool)
                or not 1 <= max_search_uses <= 10
            ):
                raise ValueError(
                    f"Target {target['target_id']!r} max_search_uses "
                    "must be an integer from 1 through 10"
                )
        ids.append(str(target["target_id"]))
        if target["enabled"]:
            enabled.append(target)

    if len(ids) != len(set(ids)):
        raise ValueError("Target IDs must be unique")
    if not enabled:
        raise ValueError("Target configuration has no enabled targets")
    return enabled


def _resolve_cycle_dir(
    output_dir: Path,
    cycle_id: str,
    started_at: str,
    trigger: dict[str, Any],
    resume: bool,
) -> tuple[Path, bool]:
    matches = sorted(path for path in output_dir.rglob(cycle_id) if path.is_dir())
    if len(matches) > 1:
        raise ValueError(f"Multiple cycle directories found for {cycle_id!r}")
    if matches:
        if not resume:
            raise FileExistsError(
                f"Cycle {cycle_id!r} already exists; pass --resume to continue it"
            )
        return matches[0], True
    event_id = _safe_path_segment(trigger.get("event_id") or "unassigned-event")
    archive = trigger.get("archive")
    if isinstance(archive, dict) and archive.get("relative_prefix"):
        relative = _safe_relative_prefix(str(archive["relative_prefix"]), event_id)
        event_root = output_dir.joinpath(*relative.split("/"))
    else:
        archive_time = _archive_datetime(trigger, started_at)
        event_root = (
            output_dir
            / f"{archive_time.year:04d}"
            / archive_time.strftime("%B")
            / _week_folder_name(archive_time)
            / event_id
        )
    return event_root / f"{event_id}_AI" / "runs" / cycle_id, False


def _archive_datetime(trigger: dict[str, Any], fallback: str) -> datetime:
    for value in (
        trigger.get("timestamp"),
        trigger.get("sent_at"),
        trigger.get("generated_at"),
        fallback,
    ):
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _week_folder_name(when: datetime) -> str:
    month_start = when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if when.month == 12:
        next_month = month_start.replace(year=when.year + 1, month=1)
    else:
        next_month = month_start.replace(month=when.month + 1)
    month_end = next_month - timedelta(days=1)
    week_start = max(when - timedelta(days=when.weekday()), month_start)
    week_end = min(week_start + timedelta(days=6), month_end)
    return f"{week_start.strftime('%b_%d')}-{week_end.strftime('%b_%d')}"


def _safe_path_segment(value: Any) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-.")
    return safe[:128] or "unassigned-event"


def _safe_relative_prefix(value: str, event_id: str) -> str:
    parts = [_safe_path_segment(part) for part in value.split("/") if part]
    if not parts or parts[-1] != event_id:
        raise ValueError("Trigger archive.relative_prefix must end with event_id")
    if len(parts) != 4:
        raise ValueError(
            "Trigger archive.relative_prefix must be year/month/week/event_id"
        )
    return "/".join(parts)


def _write_readable_outputs(
    cycle_dir: Path,
    manifest: dict[str, Any],
    trigger: dict[str, Any],
    latest: dict[str, dict[str, Any]],
) -> None:
    records = sorted(
        latest.values(),
        key=lambda record: (
            str(record.get("target", {}).get("provider", "")),
            str(record.get("target", {}).get("target_id", "")),
            str(record.get("question", {}).get("question_id", "")),
        ),
    )
    compact = {
        "schema_version": HUMAN_OUTPUT_SCHEMA_VERSION,
        "cycle_id": manifest["cycle_id"],
        "event_id": trigger.get("event_id"),
        "message_id": trigger.get("message_id"),
        "action": trigger.get("trigger") or trigger.get("action"),
        "hazard_family": trigger.get("hazard_family"),
        "study_conditions": manifest.get("study_conditions") or ["unspecified"],
        "event": trigger.get("event"),
        "area": trigger.get("area"),
        "source": trigger.get("source"),
        "source_id": trigger.get("source_id"),
        "source_timestamp": trigger.get("timestamp"),
        "exact_trigger_file": "trigger.raw.json",
        "completed_probe_count": manifest["completed_probe_count"],
        "failed_probe_count": manifest["failed_probe_count"],
        "responses": [_compact_response(record) for record in records],
    }
    _write_json(cycle_dir / "responses.json", compact)
    _write_text(cycle_dir / "AI_RESULTS.md", _render_markdown_results(compact))


def _compact_response(record: dict[str, Any]) -> dict[str, Any]:
    target = record.get("target") or {}
    question = record.get("question") or {}
    error = record.get("error") or None
    return {
        "provider": target.get("provider"),
        "target_id": target.get("target_id"),
        "requested_model": target.get("model"),
        "resolved_model": record.get("resolved_model"),
        "question_id": question.get("question_id"),
        "category": question.get("category"),
        "prompt": question.get("prompt"),
        "status": record.get("status"),
        "search_requested": record.get("search_requested"),
        "search_used": record.get("search_used"),
        "search_count": record.get("search_count"),
        "citations": record.get("citations") or [],
        "response": record.get("response_text"),
        "error": error.get("message") if isinstance(error, dict) else error,
    }


def _write_latest_convenience_files(
    cycle_dir: Path, manifest: dict[str, Any]
) -> None:
    if manifest.get("cycle_status") != "complete" or cycle_dir.parent.name != "runs":
        return
    ai_root = cycle_dir.parent.parent
    for filename in ("AI_RESULTS.md", "responses.json", "trigger.raw.json"):
        source = cycle_dir / filename
        if not source.is_file():
            continue
        target = ai_root / filename
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(source.read_bytes())
        temporary.replace(target)
    _write_json(
        ai_root / "LATEST.json",
        {
            "schema_version": 1,
            "cycle_id": manifest.get("cycle_id"),
            "message_id": manifest.get("ground_truth_message_id"),
            "cycle_completed_at": manifest.get("cycle_completed_at"),
            "study_conditions": manifest.get("study_conditions") or ["unspecified"],
            "run_directory": f"runs/{cycle_dir.name}",
        },
    )


def _render_markdown_results(results: dict[str, Any]) -> str:
    lines = [
        "# AI Probe Results",
        "",
        f"- **Event ID:** {results.get('event_id') or 'N/A'}",
        f"- **Trigger message:** {results.get('message_id') or results['cycle_id']}",
        f"- **Action:** {results.get('action') or 'manual'}",
        f"- **Hazard:** {results.get('hazard_family') or 'N/A'}",
        f"- **Study condition:** {', '.join(results.get('study_conditions') or [])}",
        f"- **Event:** {results.get('event') or 'N/A'}",
        f"- **Area:** {results.get('area') or 'N/A'}",
        f"- **Official source:** {results.get('source') or 'N/A'} "
        f"({results.get('source_id') or 'N/A'})",
        f"- **Source time:** {results.get('source_timestamp') or 'N/A'}",
        f"- **Probe status:** {results['completed_probe_count']} completed, "
        f"{results['failed_probe_count']} failed",
        "- **Exact ground-truth trigger:** [`trigger.raw.json`](trigger.raw.json)",
        "- **Compact machine-readable results:** [`responses.json`](responses.json)",
        "",
        "---",
        "",
    ]
    current_target: tuple[Any, Any, Any] | None = None
    for response in results["responses"]:
        target = (
            response.get("provider"),
            response.get("target_id"),
            response.get("resolved_model") or response.get("requested_model"),
        )
        if target != current_target:
            current_target = target
            lines.extend(
                [
                    f"## {target[0]} — {target[2]}",
                    "",
                    f"Target: `{target[1]}`",
                    "",
                ]
            )
        lines.extend(
            [
                f"### {response.get('question_id')} — {response.get('category')}",
                "",
                "**Prompt**",
                "",
                str(response.get("prompt") or "N/A"),
                "",
                f"**Live search:** {_search_summary(response)}",
                "",
                "**Response**",
                "",
                str(response.get("response") or response.get("error") or "No response"),
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _search_summary(response: dict[str, Any]) -> str:
    if not response.get("search_requested"):
        return "not requested"
    count = response.get("search_count")
    if response.get("search_used"):
        return f"used ({count} search call{'s' if count != 1 else ''} recorded)"
    return "requested; no search call was recorded"


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


def _write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(data, encoding="utf-8")
    temporary.replace(path)
