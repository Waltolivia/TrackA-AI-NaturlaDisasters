"""Immediate, durable S3 copies of ground-truth event files.

Local SQLite and reports remain the working copy. S3 synchronization is
additive: files are never deleted locally by this module, and a failed upload
is kept in a small local retry queue.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .archive import event_archive_location

log = logging.getLogger("disaster-monitor")


class S3ArchiveError(RuntimeError):
    """Raised when immediate S3 archiving cannot be configured."""


def _s3_client(region: str, session=None):
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise S3ArchiveError(
            "boto3 is required for S3 archiving; install requirements.txt"
        ) from exc
    factory = session or boto3
    return factory.client("s3", region_name=region)


def _join_key(*parts: object) -> str:
    return "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _row(row: Any) -> dict[str, Any]:
    result = dict(row)
    for source, destination in (("raw_json", "raw"), ("geometry_json", "geometry")):
        value = result.pop(source, None)
        if value:
            try:
                result[destination] = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                result[destination] = value
    return result


class S3EventArchive:
    """Queue and upload current ground-truth snapshots under one event prefix."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        prefix: str = "disaster_monitor-v5/archive",
        pending_path: str | Path = "data/s3_pending",
        archive_path: str | Path = "archive",
        client=None,
    ):
        if not bucket.strip():
            raise ValueError("S3 bucket cannot be empty")
        self.bucket = bucket.strip()
        self.region = region
        self.prefix = prefix.strip("/")
        self.pending_path = Path(pending_path)
        self.archive_path = Path(archive_path)
        self.pending_path.mkdir(parents=True, exist_ok=True)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _s3_client(self.region)
        return self._client

    def schedule(self, event_id: int) -> Path:
        """Persist a retry marker immediately after a local report is written."""
        target = self.pending_path / f"event-{int(event_id)}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"event_id": int(event_id)}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def sync_pending(self, db, *, limit: int | None = None) -> dict[str, int]:
        markers = sorted(self.pending_path.glob("event-*.json"))
        if limit is not None:
            markers = markers[:limit]
        result = {"attempted": 0, "uploaded": 0, "failed": 0}
        for marker in markers:
            result["attempted"] += 1
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
                self.upload_event(db, int(payload["event_id"]))
                marker.unlink(missing_ok=True)
                result["uploaded"] += 1
            except Exception as exc:  # noqa: BLE001 - marker must remain for retry
                result["failed"] += 1
                log.warning("S3 ground-truth upload pending marker=%s error=%s", marker, exc)
        return result

    def upload_event(self, db, event_id: int) -> dict[str, Any]:
        event = db.get_event(event_id)
        if event is None:
            raise KeyError(f"Ground-truth event no longer exists: {event_id}")
        alerts = db.alerts_for_event(event_id)
        location = event_archive_location(event)
        public_id = str(event["public_id"])
        weather_prefix = _join_key(
            self.prefix,
            location["relative_prefix"],
            f"{public_id}_weather",
        )

        event_payload = _row(event)
        alerts_payload = [_row(alert) for alert in alerts]
        report_path = self._report_path(event)
        objects: list[tuple[str, bytes, str]] = [
            ("event.json", _json_bytes(event_payload), "application/json"),
            ("alerts.json", _json_bytes(alerts_payload), "application/json"),
        ]
        if report_path.is_file():
            objects.insert(
                0,
                ("EVENT_REPORT.txt", report_path.read_bytes(), "text/plain; charset=utf-8"),
            )

        uploaded_keys = []
        for filename, body, content_type in objects:
            key = _join_key(weather_prefix, filename)
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
            uploaded_keys.append(key)

        manifest_key = _join_key(weather_prefix, "archive_manifest.json")
        manifest = {
            "schema_version": 1,
            "event_id": public_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "objects": uploaded_keys,
        }
        self.client.put_object(
            Bucket=self.bucket,
            Key=manifest_key,
            Body=_json_bytes(manifest),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        log.info(
            "S3 ground truth uploaded event=%s bucket=%s prefix=%s objects=%d",
            public_id,
            self.bucket,
            weather_prefix,
            len(uploaded_keys) + 1,
        )
        return {"event_id": public_id, "prefix": weather_prefix, "objects": len(uploaded_keys) + 1}

    def _report_path(self, event) -> Path:
        from .archive import event_report_path

        return event_report_path(event, self.archive_path)
