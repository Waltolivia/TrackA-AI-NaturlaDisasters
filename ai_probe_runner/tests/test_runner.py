import json
from pathlib import Path

import pytest

from ai_probe_runner.questions import build_questions
from ai_probe_runner.runner import run_cycle


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
    with pytest.raises(ValueError, match="Question bank not found"):
        build_questions(trigger, bank_dir)
