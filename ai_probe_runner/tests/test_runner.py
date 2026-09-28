import json
import sys
from pathlib import Path

import pytest

from ai_probe_runner.questions import build_questions, normalize_trigger
from ai_probe_runner.runner import load_targets, run_cycle
from ai_probe_runner import cli


def test_example_targets_are_three_provider_no_search_baseline() -> None:
    config_path = Path(__file__).parents[1] / "config" / "targets.example.json"
    targets = json.loads(config_path.read_text(encoding="utf-8"))

    assert {
        (target["provider"], target["model"], target["browsing"])
        for target in targets
        if target.get("enabled", True)
    } == {
        ("openai", "gpt-5.6-luna", False),
        ("anthropic", "claude-sonnet-5-5", False),
        ("google", "gemini-3.5-flash-lite", False),
    }
    assert all(target.get("target_id") for target in targets)
    assert all(target.get("interface") for target in targets)


def write_banks(bank_dir: Path) -> None:
    (bank_dir / "hazards").mkdir(parents=True)
    (bank_dir / "general.json").write_text(json.dumps([{
        "question_id": "general",
        "category": "situational",
        "template": "Is {area} affected by {event}?",
    }]))
    (bank_dir / "hazards" / "flood.json").write_text(json.dumps([{
        "question_id": "flood",
        "category": "protective-action",
        "template": "What should people in {area} do?",
    }]))


def test_trigger_selects_general_and_hazard_banks(tmp_path: Path) -> None:
    bank_dir = tmp_path / "banks"
    write_banks(bank_dir)
    trigger = {
        "source": "NWS",
        "source_id": "alert-1",
        "hazard_family": "flood",
        "event": "Flash Flood Warning",
        "area": "Test County",
    }
    questions, paths = build_questions(trigger, bank_dir)
    assert [question["question_id"] for question in questions] == ["general", "flood"]
    assert len(paths) == 2
    assert questions[0]["prompt"] == "Is Test County affected by Flash Flood Warning?"


def test_v2_outbox_trigger_is_normalized_for_ai_questions() -> None:
    trigger = {
        "schema_version": 2,
        "trigger": "NEW_EVENT",
        "event_id": "event-00000001",
        "event_type": "Flash Flood Warning",
        "event_status": "ACTIVE",
        "location": "Test County, Utah",
        "headline": "Flash Flood Warning for Test County",
        "source": "NWS",
        "source_alert_id": "alert-1",
        "sent_at": "2026-09-28T12:00:00Z",
        "generated_at": "2026-09-28T12:01:00Z",
    }

    normalized = normalize_trigger(trigger)

    assert normalized["hazard_family"] == "flood"
    assert normalized["event"] == "Flash Flood Warning"
    assert normalized["area"] == "Test County, Utah"
    assert normalized["source_id"] == "alert-1"
    assert normalized["timestamp"] == "2026-09-28T12:00:00Z"


def test_v2_null_aliases_are_filled_from_collector_fields() -> None:
    normalized = normalize_trigger({
        "schema_version": 2,
        "trigger": "NEW_EVENT",
        "event_id": "event-00000001",
        "event_type": "Flash Flood Warning",
        "location": "Test County, Utah",
        "source": "NWS",
        "source_alert_id": "alert-1",
        "sent_at": "2026-09-28T12:00:00Z",
        "source_id": None,
        "event": None,
        "area": None,
        "timestamp": None,
        "hazard_family": None,
    })

    assert normalized["source_id"] == "alert-1"
    assert normalized["event"] == "Flash Flood Warning"
    assert normalized["area"] == "Test County, Utah"
    assert normalized["timestamp"] == "2026-09-28T12:00:00Z"
    assert normalized["hazard_family"] == "flood"


def test_minimal_v2_handoff_has_safe_provenance_fallbacks() -> None:
    normalized = normalize_trigger({
        "schema_version": 2,
        "trigger": "NEW_EVENT",
        "event_id": "event-00000001",
        "event_type": "Flash Flood Warning",
        "location": "Test County, Utah",
        "generated_at": "2026-09-28T12:01:00Z",
    })

    assert normalized["source"] == "disaster-monitor-v2"
    assert normalized["source_id"] == "event-00000001"
    assert normalized["timestamp"] == "2026-09-28T12:01:00Z"
    assert normalized["hazard_family"] == "flood"


def test_v2_lifecycle_trigger_does_not_start_ai_probes() -> None:
    trigger = {
        "schema_version": 2,
        "trigger": "EVENT_ENDED",
        "event_id": "event-00000001",
        "event_type": "flood",
        "location": "Test County, Utah",
    }
    with pytest.raises(ValueError, match="only run"):
        normalize_trigger(trigger)


@pytest.mark.parametrize(
    ("event_type", "family"),
    [
        ("Flash Flood Warning", "flood"),
        ("Floods", "flood"),
        ("Wildfires", "wildfire"),
        ("Red Flag Warning", "wildfire"),
        ("Hurricane Warning", "tropical_cyclone"),
        ("Tropical Storm Watch", "tropical_cyclone"),
        ("Tornado Warning", "tornado"),
        ("Earthquakes", "earthquake"),
    ],
)
def test_v2_event_terms_select_expected_bank(event_type: str, family: str) -> None:
    normalized = normalize_trigger({
        "schema_version": 2,
        "trigger": "NEW_EVENT",
        "event_id": "event-1",
        "event_type": event_type,
        "location": "Test Area",
        "source": "test",
        "source_alert_id": "alert-1",
    })
    assert normalized["hazard_family"] == family


def test_unsupported_v2_hazard_has_actionable_error() -> None:
    trigger = {
        "schema_version": 2,
        "trigger": "NEW_EVENT",
        "event_id": "event-00000001",
        "event_type": "volcano",
        "location": "Test County, Utah",
        "source": "NASA_EONET",
        "source_alert_id": "eonet-1",
    }
    with pytest.raises(ValueError, match="Unsupported disaster-monitor event_type"):
        normalize_trigger(trigger)


def test_mock_cycle_archives_trigger_questions_and_responses(tmp_path: Path) -> None:
    bank_dir = tmp_path / "banks"
    write_banks(bank_dir)
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps([{
        "target_id": "mock",
        "provider": "mock",
        "model": "mock-v1",
        "interface": "local-mock",
        "browsing": False,
        "enabled": True,
    }]))
    trigger = {
        "cycle_id": "shared-cycle",
        "source": "NWS",
        "source_id": "alert-1",
        "version_hash": "v1",
        "hazard_family": "flood",
        "event": "Flash Flood Warning",
        "area": "Test County",
    }

    result = run_cycle(
        trigger=trigger,
        targets_path=targets,
        bank_dir=bank_dir,
        output_dir=tmp_path / "data",
    )

    cycle_dir = Path(result["cycle_dir"])
    manifest = json.loads((cycle_dir / "manifest.json").read_text())
    records = [
        json.loads(line)
        for line in (cycle_dir / "probes.jsonl").read_text().splitlines()
    ]
    assert result["cycle_id"] == "shared-cycle"
    assert manifest["completed_probe_count"] == 2
    assert manifest["failed_probe_count"] == 0
    assert (cycle_dir / "trigger.raw.json").is_file()
    assert (cycle_dir / "trigger.json").is_file()
    assert (cycle_dir / "questions.json").is_file()
    assert all(record["status"] == "success" for record in records)


def test_unknown_hazard_requires_a_bank(tmp_path: Path) -> None:
    bank_dir = tmp_path / "banks"
    write_banks(bank_dir)
    trigger = {
        "source": "NWS",
        "source_id": "alert-1",
        "hazard_family": "unknown",
        "event": "Unknown Warning",
        "area": "Test County",
    }
    with pytest.raises(ValueError, match="Unsupported disaster-monitor event_type"):
        build_questions(trigger, bank_dir)


def test_target_config_requires_unique_ids_and_enabled_target(tmp_path: Path) -> None:
    targets = tmp_path / "targets.json"
    target = {
        "target_id": "duplicate",
        "provider": "mock",
        "model": "mock-v1",
        "interface": "local-mock",
        "browsing": False,
        "enabled": True,
    }
    targets.write_text(json.dumps([target, target]), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_targets(targets)


def test_project_flood_bank_renders_nine_questions() -> None:
    project_dir = Path(__file__).parents[1]
    trigger = json.loads(
        (project_dir / "examples" / "trigger.flash-flood.json").read_text(
            encoding="utf-8"
        )
    )
    questions, _ = build_questions(trigger, project_dir / "config" / "question_banks")
    assert len(questions) == 9
    assert len({question["question_id"] for question in questions}) == 9
    assert all("Test County, Utah" in question["prompt"] for question in questions)


def test_cli_fail_on_probe_error_returns_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trigger_path = tmp_path / "trigger.json"
    trigger_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "run_cycle",
        lambda **kwargs: {"cycle_id": "test", "failed_probe_count": 1},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ai-probe-runner",
            "--trigger",
            str(trigger_path),
            "--fail-on-probe-error",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
