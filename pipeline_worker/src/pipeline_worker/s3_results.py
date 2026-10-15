"""Upload completed AI cycles into the ground-truth event's S3 folder."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("pipeline-worker")
MARKER_NAME = ".s3-uploaded.json"


def _s3_client(region: str, session=None):
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "boto3 is required for S3 result uploads; run uv sync for pipeline_worker"
        ) from exc
    factory = session or boto3
    return factory.client("s3", region_name=region)


def _join_key(*parts: object) -> str:
    return "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))


def _safe_segment(value: Any) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-.")
    return safe[:128] or "unknown"


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


def _fallback_event_prefix(trigger: dict[str, Any], event_id: str) -> str:
    for value in (trigger.get("sent_at"), trigger.get("generated_at")):
        if not value:
            continue
        try:
            when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            when = when.astimezone(timezone.utc)
            return _join_key(
                f"{when.year:04d}",
                when.strftime("%B"),
                _week_folder_name(when),
                event_id,
            )
        except ValueError:
            continue
    raise ValueError("Trigger has no archive location or usable timestamp")


def _event_prefix(trigger: dict[str, Any], event_id: str) -> str:
    archive = trigger.get("archive")
    if isinstance(archive, dict) and archive.get("relative_prefix"):
        parts = [
            _safe_segment(part)
            for part in str(archive["relative_prefix"]).split("/")
            if part
        ]
        if len(parts) != 4 or parts[-1] != event_id:
            raise ValueError(
                "Trigger archive.relative_prefix must be year/month/week/event_id"
            )
        return "/".join(parts)
    log.warning(
        "trigger lacks authoritative archive location; using timestamp fallback event=%s",
        event_id,
    )
    return _fallback_event_prefix(trigger, event_id)


def _content_type(path: Path) -> str:
    if path.suffix == ".md":
        return "text/markdown; charset=utf-8"
    if path.suffix in {".json", ".jsonl"}:
        return "application/json"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class S3ResultArchive:
    """Idempotently mirror complete AI cycles to S3.

    A local marker is written only after every object succeeds. Missing markers
    are retried independently of AI jobs, so an S3 outage cannot spend API
    credits by rerunning already-complete probes.
    """

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        prefix: str = "disaster_monitor-v5/archive",
        client=None,
    ):
        if not bucket.strip():
            raise ValueError("S3 bucket cannot be empty")
        self.bucket = bucket.strip()
        self.region = region
        self.prefix = prefix.strip("/")
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _s3_client(self.region)
        return self._client

    def upload_pending(self, output_dir: Path, *, limit: int = 10) -> dict[str, int]:
        result = {"attempted": 0, "uploaded": 0, "failed": 0}
        affected_events: set[str] = set()
        for manifest_path in sorted(Path(output_dir).rglob("manifest.json")):
            if result["attempted"] >= limit:
                break
            cycle_dir = manifest_path.parent
            if (cycle_dir / MARKER_NAME).is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if manifest.get("cycle_status") != "complete":
                continue
            result["attempted"] += 1
            try:
                marker = self.upload_cycle(cycle_dir)
                affected_events.add(str(marker["event_id"]))
                result["uploaded"] += 1
            except Exception as exc:  # noqa: BLE001 - leave unmarked for retry
                result["failed"] += 1
                log.warning("S3 AI upload remains pending cycle=%s error=%s", cycle_dir, exc)
        # A delayed older run may have just uploaded after a newer run. Publish
        # the newest local cycle again so the convenient top-level files never
        # point backward in time.
        for event_id in affected_events:
            latest = self._latest_cycle_for_event(Path(output_dir), event_id)
            if latest is not None:
                self.upload_cycle(latest)
        return result

    def upload_cycle(self, cycle_dir: Path) -> dict[str, Any]:
        cycle_dir = Path(cycle_dir)
        manifest = json.loads((cycle_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("cycle_status") != "complete":
            raise ValueError(f"AI cycle is not complete: {cycle_dir}")
        trigger = json.loads((cycle_dir / "trigger.raw.json").read_text(encoding="utf-8"))
        event_id = _safe_segment(trigger.get("event_id") or manifest.get("ground_truth_event_id"))
        message_id = _safe_segment(trigger.get("message_id") or manifest.get("cycle_id"))
        relative_event = _event_prefix(trigger, event_id)
        ai_prefix = _join_key(self.prefix, relative_event, f"{event_id}_AI")
        run_prefix = _join_key(ai_prefix, "runs", message_id)

        files = sorted(
            path
            for path in cycle_dir.rglob("*")
            if path.is_file()
            and path.name != MARKER_NAME
            and not path.name.endswith(".tmp")
        )
        uploaded_keys = []
        for path in files:
            key = _join_key(run_prefix, path.relative_to(cycle_dir).as_posix())
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType=_content_type(path),
                ServerSideEncryption="AES256",
            )
            uploaded_keys.append(key)

        # These two convenient files always point at the most recently
        # completed trigger while immutable run folders retain full history.
        for filename in ("AI_RESULTS.md", "responses.json", "trigger.raw.json"):
            path = cycle_dir / filename
            if path.is_file():
                key = _join_key(ai_prefix, filename)
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=path.read_bytes(),
                    ContentType=_content_type(path),
                    ServerSideEncryption="AES256",
                )
                uploaded_keys.append(key)

        latest = {
            "schema_version": 1,
            "event_id": event_id,
            "message_id": message_id,
            "cycle_id": manifest.get("cycle_id"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "run_prefix": run_prefix,
        }
        latest_key = _join_key(ai_prefix, "LATEST.json")
        self.client.put_object(
            Bucket=self.bucket,
            Key=latest_key,
            Body=(json.dumps(latest, indent=2) + "\n").encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        uploaded_keys.append(latest_key)

        marker = {
            "event_id": event_id,
            "message_id": message_id,
            "bucket": self.bucket,
            "prefix": run_prefix,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "object_count": len(uploaded_keys),
        }
        marker_path = cycle_dir / MARKER_NAME
        temporary = marker_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
        temporary.replace(marker_path)
        log.info(
            "S3 AI results uploaded event=%s message=%s bucket=%s prefix=%s objects=%d",
            event_id,
            message_id,
            self.bucket,
            run_prefix,
            len(uploaded_keys),
        )
        return marker

    @staticmethod
    def _latest_cycle_for_event(output_dir: Path, event_id: str) -> Path | None:
        latest: tuple[str, Path] | None = None
        for manifest_path in output_dir.rglob("manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("cycle_status") != "complete":
                    continue
                trigger = json.loads(
                    (manifest_path.parent / "trigger.raw.json").read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, json.JSONDecodeError):
                continue
            candidate_event = _safe_segment(
                trigger.get("event_id") or manifest.get("ground_truth_event_id")
            )
            if candidate_event != event_id:
                continue
            completed = str(manifest.get("cycle_completed_at") or "")
            candidate = (completed, manifest_path.parent)
            if latest is None or candidate[0] > latest[0]:
                latest = candidate
        return latest[1] if latest else None
