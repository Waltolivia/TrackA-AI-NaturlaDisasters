from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_TRIGGER_FIELDS = {"source", "source_id", "hazard_family", "event", "area"}
SUPPORTED_HAZARD_FAMILIES = {
    "earthquake",
    "flood",
    "tornado",
    "tropical_cyclone",
    "wildfire",
}
PROBE_TRIGGER_TYPES = {
    "NEW_EVENT",
    "ESCALATION",
    "STATUS_CHANGED",
    "SEVERITY_CHANGED",
}

HAZARD_TERMS = {
    "earthquake": ("earthquake", "earthquakes"),
    "flood": ("flash flood", "flood", "floods", "storm surge"),
    "tornado": ("tornado", "tornadoes"),
    "tropical_cyclone": (
        "hurricane",
        "tropical cyclone",
        "tropical storm",
    ),
    "wildfire": (
        "wildfire",
        "wildfires",
        "fire weather",
        "red flag",
    ),
}


class StrictValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        raise ValueError(f"Question template requires missing trigger field: {key}")


def load_trigger(path: Path) -> dict[str, Any]:
    trigger = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(trigger, dict):
        raise ValueError("Trigger JSON must be one object")
    return trigger


def normalize_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical trigger shape used by prompts and archived records.

    The function accepts the original AI-runner contract and the JSON emitted
    by disaster_monitor-v2 or disaster_monitor-v5. Original collector fields
    are kept; canonical aliases are added without modifying the caller's input.
    """
    if not isinstance(trigger, dict):
        raise ValueError("Trigger JSON must be one object")

    normalized = dict(trigger)
    disaster = normalized.get("disaster")
    is_v3 = (
        normalized.get("schema_version") == 3
        and isinstance(disaster, dict)
        and "message_id" in normalized
        and "action" in normalized
    )
    is_v2 = all(key in normalized for key in ("event_id", "event_type", "location"))

    if is_v3:
        trigger_type = normalized.get("action")
        if trigger_type not in PROBE_TRIGGER_TYPES:
            allowed = ", ".join(sorted(PROBE_TRIGGER_TYPES))
            raise ValueError(
                "AI probes only run for disaster-monitor actions "
                f"{allowed}; received {trigger_type!r}"
            )

        event_type = disaster.get("type")
        location = disaster.get("location")
        normalized["trigger"] = trigger_type
        normalized["event_type"] = event_type
        normalized["location"] = location
        normalized["source"] = normalized.get("source") or "disaster-monitor-v5"
        normalized["source_id"] = (
            normalized.get("source_id")
            or normalized.get("source_alert_id")
            or normalized.get("message_id")
            or normalized.get("event_id")
        )
        normalized["event"] = (
            normalized.get("event")
            or disaster.get("name")
            or event_type
            or normalized.get("headline")
        )
        normalized["area"] = normalized.get("area") or location
        normalized["timestamp"] = (
            normalized.get("timestamp")
            or normalized.get("sent_at")
            or normalized.get("generated_at")
        )
        normalized["detected_at"] = normalized.get("detected_at") or normalized.get(
            "generated_at"
        )
        normalized["hazard_family"] = normalized.get(
            "hazard_family"
        ) or hazard_family_for(
            str(event_type or ""),
            str(normalized.get("headline") or disaster.get("name") or ""),
        )
    elif is_v2:
        trigger_type = normalized.get("trigger")
        if trigger_type not in PROBE_TRIGGER_TYPES:
            allowed = ", ".join(sorted(PROBE_TRIGGER_TYPES))
            raise ValueError(
                "AI probes only run for disaster-monitor triggers "
                f"{allowed}; received {trigger_type!r}"
            )

        if not normalized.get("source"):
            normalized["source"] = "disaster-monitor-v2"
        if not normalized.get("source_id"):
            normalized["source_id"] = normalized.get(
                "source_alert_id"
            ) or normalized.get("event_id")
        if not normalized.get("event"):
            normalized["event"] = normalized.get("event_type") or normalized.get(
                "headline"
            )
        if not normalized.get("area"):
            normalized["area"] = normalized.get("location")
        if not normalized.get("timestamp"):
            normalized["timestamp"] = normalized.get("sent_at") or normalized.get(
                "generated_at"
            )
        if not normalized.get("detected_at"):
            normalized["detected_at"] = normalized.get("generated_at")
        if not normalized.get("hazard_family"):
            normalized["hazard_family"] = hazard_family_for(
                str(normalized.get("event_type") or ""),
                str(normalized.get("headline") or ""),
            )
    else:
        normalized.setdefault(
            "timestamp",
            normalized.get("sent_at")
            or normalized.get("effective")
            or normalized.get("detected_at")
            or "Unknown",
        )
        if normalized.get("hazard_family"):
            normalized["hazard_family"] = hazard_family_for(
                str(normalized["hazard_family"]),
                str(normalized.get("event") or ""),
            )

    missing = sorted(
        field
        for field in REQUIRED_TRIGGER_FIELDS
        if normalized.get(field) is None or str(normalized.get(field)).strip() == ""
    )
    if missing:
        raise ValueError(f"Trigger is missing required fields: {', '.join(missing)}")
    return normalized


def hazard_family_for(event_type: str, headline: str = "") -> str:
    direct = event_type.strip().lower().replace("-", "_").replace(" ", "_")
    if direct in SUPPORTED_HAZARD_FAMILIES:
        return direct

    searchable = f"{event_type} {headline}".lower().replace("_", " ")
    for family, terms in HAZARD_TERMS.items():
        if any(term in searchable for term in terms):
            return family

    supported = ", ".join(sorted(SUPPORTED_HAZARD_FAMILIES))
    raise ValueError(
        f"Unsupported disaster-monitor event_type {event_type!r}. "
        f"Supported AI question-bank families: {supported}"
    )


def build_questions(
    trigger: dict[str, Any], bank_dir: Path
) -> tuple[list[dict[str, Any]], list[Path]]:
    trigger = normalize_trigger(trigger)

    hazard_family = str(trigger["hazard_family"])
    bank_paths = [
        bank_dir / "general.json",
        bank_dir / "hazards" / f"{hazard_family}.json",
    ]
    missing_banks = [str(path) for path in bank_paths if not path.is_file()]
    if missing_banks:
        raise ValueError(f"Question bank not found: {', '.join(missing_banks)}")

    values = StrictValues(
        {
            key: "Unknown" if value is None else str(value)
            for key, value in trigger.items()
        }
    )
    questions: list[dict[str, Any]] = []
    for bank_path in bank_paths:
        bank = json.loads(bank_path.read_text(encoding="utf-8"))
        if not isinstance(bank, list):
            raise ValueError(f"Question bank must be a JSON list: {bank_path}")
        for template in bank:
            if not isinstance(template, dict):
                raise ValueError(f"Every question must be a JSON object: {bank_path}")
            required = {"question_id", "category", "template"}
            missing = sorted(required - template.keys())
            if missing:
                raise ValueError(
                    f"Question in {bank_path} is missing fields: {', '.join(missing)}"
                )
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
