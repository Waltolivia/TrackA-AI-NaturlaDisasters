from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_TRIGGER_FIELDS = {"source", "source_id", "hazard_family", "event", "area"}


class StrictValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        raise ValueError(f"Question template requires missing trigger field: {key}")


def load_trigger(path: Path) -> dict[str, Any]:
    trigger = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(trigger, dict):
        raise ValueError("Trigger JSON must be one object")
    return trigger


def build_questions(
    trigger: dict[str, Any], bank_dir: Path
) -> tuple[list[dict[str, Any]], list[Path]]:
    missing = sorted(REQUIRED_TRIGGER_FIELDS - trigger.keys())
    if missing:
        raise ValueError(f"Trigger is missing required fields: {', '.join(missing)}")

    hazard_family = str(trigger["hazard_family"])
    bank_paths = [
        bank_dir / "general.json",
        bank_dir / "hazards" / f"{hazard_family}.json",
    ]
    missing_banks = [str(path) for path in bank_paths if not path.is_file()]
    if missing_banks:
        raise ValueError(f"Question bank not found: {', '.join(missing_banks)}")

    values = StrictValues({
        key: "Unknown" if value is None else str(value)
        for key, value in trigger.items()
    })
    questions: list[dict[str, Any]] = []
    for bank_path in bank_paths:
        bank = json.loads(bank_path.read_text(encoding="utf-8"))
        if not isinstance(bank, list):
            raise ValueError(f"Question bank must be a JSON list: {bank_path}")
        for template in bank:
            question = dict(template)
            question["prompt"] = str(question.pop("template")).format_map(values)
            question["hazard_family"] = hazard_family
            question["ground_truth_source"] = trigger["source"]
            question["ground_truth_source_id"] = trigger["source_id"]
            questions.append(question)

    ids = [question.get("question_id") for question in questions]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("Question IDs must exist and be unique across selected banks")
    return questions, bank_paths
