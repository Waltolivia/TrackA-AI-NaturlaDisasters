from __future__ import annotations

import json
from pathlib import Path

from pipeline_worker.config import WorkerConfig
from pipeline_worker.worker import PipelineWorker

REPOSITORY_ROOT = Path(__file__).parents[2]


def v5_payload(action: str = "NEW_EVENT", event_type: str = "flash flood") -> dict:
    return {
        "schema_version": 3,
        "message_id": f"MSG-{action.lower().replace('_', '-')}",
        "action": action,
        "event_id": "EVT-00000001",
        "disaster": {
            "type": event_type,
            "name": None,
            "location": "Test County, Utah",
        },
        "severity": "Severe",
        "status": "WARNING",
        "event_lifecycle": "ACTIVE",
        "source": "NWS",
        "source_alert_id": "alert-1",
        "sent_at": "2026-09-28T12:00:00Z",
        "generated_at": "2026-09-28T12:01:00Z",
        "headline": "Flash Flood Warning for Test County",
    }


def config(tmp_path: Path, *, layout: str = "v5") -> WorkerConfig:
    return WorkerConfig(
        outbox=tmp_path / "outbox",
        state_db=tmp_path / "pipeline" / "worker.db",
        targets=REPOSITORY_ROOT / "ai_probe_runner" / "config" / "targets.mock.json",
        question_bank_dir=(
            REPOSITORY_ROOT / "ai_probe_runner" / "config" / "question_banks"
        ),
        output_dir=tmp_path / "pipeline" / "results",
        ai_project=REPOSITORY_ROOT / "ai_probe_runner",
        queue_layout=layout,
        retry_base_seconds=0,
        job_timeout_seconds=60,
    )


def test_v5_message_runs_once_and_is_acknowledged(tmp_path: Path) -> None:
    worker = PipelineWorker(config(tmp_path))
    trigger = worker.config.outbox / "pending" / "trigger.json"
    trigger.write_text(json.dumps(v5_payload()), encoding="utf-8")

    first = worker.run_once()
    assert first["processed"] == 1
    assert first["succeeded"] == 1
    assert first["state"]["counts"] == {"SUCCEEDED": 1}
    assert not trigger.exists()
    assert (worker.config.outbox / "completed" / "trigger.json").is_file()

    job = worker.database.get("MSG-new-event")
    assert job is not None
    manifest = json.loads(
        (Path(job["cycle_dir"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["completed_probe_count"] == 9
    assert manifest["failed_probe_count"] == 0
    assert manifest["ground_truth_message_id"] == "MSG-new-event"

    second = worker.run_once()
    assert second["processed"] == 0
    assert second["state"]["counts"] == {"SUCCEEDED": 1}

    duplicate = worker.config.outbox / "pending" / "duplicate.json"
    duplicate.write_text(json.dumps(v5_payload()), encoding="utf-8")
    third = worker.run_once()
    assert third["processed"] == 0
    assert third["discovery"]["duplicate"] == 1
    assert not duplicate.exists()


def test_lifecycle_message_is_skipped_and_acknowledged(tmp_path: Path) -> None:
    worker = PipelineWorker(config(tmp_path))
    trigger = worker.config.outbox / "pending" / "ended.json"
    trigger.write_text(json.dumps(v5_payload("EVENT_ENDED")), encoding="utf-8")

    result = worker.run_once()

    assert result["processed"] == 0
    assert result["discovery"]["skipped"] == 1
    assert result["state"]["counts"] == {"SKIPPED": 1}
    assert (worker.config.outbox / "completed" / "ended.json").is_file()


def test_unsupported_hazard_is_skipped_without_retries(tmp_path: Path) -> None:
    worker = PipelineWorker(config(tmp_path))
    trigger = worker.config.outbox / "pending" / "volcano.json"
    payload = v5_payload(event_type="volcano")
    payload["headline"] = "Volcano eruption"
    trigger.write_text(json.dumps(payload), encoding="utf-8")

    result = worker.run_once()

    assert result["processed"] == 0
    assert result["discovery"]["skipped"] == 1
    job = worker.database.get("MSG-new-event")
    assert job is not None
    assert "Unsupported" in job["last_error"]


def test_invalid_json_is_moved_to_failed(tmp_path: Path) -> None:
    worker = PipelineWorker(config(tmp_path))
    trigger = worker.config.outbox / "pending" / "broken.json"
    trigger.write_text("{not valid JSON", encoding="utf-8")

    result = worker.run_once()

    assert result["processed"] == 0
    assert result["discovery"]["invalid"] == 1
    assert result["state"]["counts"] == {"INVALID": 1}
    assert (worker.config.outbox / "failed" / "broken.json").is_file()


def test_coordinate_only_eonet_location_is_skipped(tmp_path: Path) -> None:
    worker = PipelineWorker(config(tmp_path))
    trigger = worker.config.outbox / "pending" / "eonet.json"
    payload = v5_payload(event_type="wildfires")
    payload["message_id"] = "MSG-eonet"
    payload["source"] = "NASA_EONET"
    payload["headline"] = "Wildfire Example Fire"
    payload["disaster"]["location"] = "coordinates=[-111.9, 40.7]"
    trigger.write_text(json.dumps(payload), encoding="utf-8")

    result = worker.run_once()

    assert result["processed"] == 0
    assert result["discovery"]["skipped"] == 1
    job = worker.database.get("MSG-eonet")
    assert job is not None
    assert "Coordinate-only" in job["last_error"]


def test_flat_v2_outbox_remains_supported(tmp_path: Path) -> None:
    worker = PipelineWorker(config(tmp_path, layout="flat"))
    trigger = worker.config.outbox / "v2-trigger.json"
    source = (
        REPOSITORY_ROOT / "ai_probe_runner" / "examples" / "trigger.flash-flood.json"
    )
    trigger.write_bytes(source.read_bytes())

    result = worker.run_once()

    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert trigger.is_file()
    assert worker.run_once()["processed"] == 0


def test_manual_retry_resets_attempt_budget(tmp_path: Path) -> None:
    worker = PipelineWorker(config(tmp_path))
    worker.database.add_job(
        job_id="MSG-retry",
        trigger_sha256="abc",
        trigger_path=tmp_path / "missing.json",
        event_id="EVT-1",
        trigger_type="NEW_EVENT",
        schema_version=3,
    )
    job = worker.database.claim_next(max_attempts=1, lease_seconds=60)
    assert job is not None
    status = worker.database.fail(
        "MSG-retry",
        max_attempts=1,
        retry_base_seconds=0,
        exit_code=1,
        stdout="",
        stderr="",
        error="test",
    )
    assert status == "DEAD"
    assert worker.database.retry("MSG-retry")
    claimed_again = worker.database.claim_next(max_attempts=1, lease_seconds=60)
    assert claimed_again is not None
    assert claimed_again["attempt_count"] == 1
