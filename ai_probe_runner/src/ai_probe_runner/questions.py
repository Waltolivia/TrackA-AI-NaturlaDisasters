from __future__ import annotations

import json
import re
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
        "typhoon",
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

HAZARD_ALIASES = {
    "earthquakes": "earthquake",
    "floods": "flood",
    "landslides": "landslide",
    "tornadoes": "tornado",
    "tsunamis": "tsunami",
    "typhoon": "tropical_cyclone",
    "typhoons": "tropical_cyclone",
    "volcanoes": "volcano",
    "wildfires": "wildfire",
}

COORDINATE_LOCATION = re.compile(
    r"^coordinates\s*=\s*\[\s*"
    r"(?P<longitude>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<latitude>-?\d+(?:\.\d+)?)\s*\]\s*$",
    re.IGNORECASE,
)


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
    by the legacy v2 collector or disaster_monitor-v5. Original collector fields
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
    normalized["location_kind"] = (
        "coordinates"
        if COORDINATE_LOCATION.fullmatch(str(normalized["area"]))
        else "named"
    )
    normalized["location_context"] = location_context(str(normalized["area"]))
    return normalized


def hazard_family_for(event_type: str, headline: str = "") -> str:
    direct = event_type.strip().lower().replace("-", "_").replace(" ", "_")
    direct = HAZARD_ALIASES.get(direct, direct)
    if direct in SUPPORTED_HAZARD_FAMILIES:
        return direct

    searchable = f"{event_type} {headline}".lower().replace("_", " ")
    for family, terms in HAZARD_TERMS.items():
        if any(term in searchable for term in terms):
            return family

    # The collector has already applied the project's natural-disaster filter.
    # Preserve an unfamiliar canonical family so it can receive the general
    # question bank instead of silently losing a research observation.  The
    # slug also prevents an event type from becoming an unsafe file path.
    fallback = re.sub(r"[^a-z0-9]+", "_", direct).strip("_")
    return fallback or "other_natural_disaster"


def location_context(area: str) -> str:
    """Render EONET longitude/latitude without requiring reverse geocoding."""
    match = COORDINATE_LOCATION.fullmatch(area.strip())
    if not match:
        return area
    return (
        f"longitude {match.group('longitude')}, latitude {match.group('latitude')} "
        "(the collector supplied coordinates but no place name)"
    )


def build_questions(
    trigger: dict[str, Any], bank_dir: Path
) -> tuple[list[dict[str, Any]], list[Path]]:
    trigger = normalize_trigger(trigger)

    hazard_family = str(trigger["hazard_family"])
    general_path = bank_dir / "general.json"
    if not general_path.is_file():
        raise ValueError(f"Question bank not found: {general_path}")
    hazard_path = bank_dir / "hazards" / f"{hazard_family}.json"
    bank_paths = [general_path]
    if hazard_path.is_file():
        bank_paths.append(hazard_path)

    values = StrictValues(
        {
            key: "Unknown" if value is None else str(value)
            for key, value in trigger.items()
        }
    )
    questions: list[dict[str, Any]] = []
    trigger_type = str(
        trigger.get("trigger") or trigger.get("action") or "NEW_EVENT"
    )
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
            trigger_types = question.pop("trigger_types", None)
            if trigger_types is not None:
                if not isinstance(trigger_types, list) or not all(
                    isinstance(value, str) for value in trigger_types
                ):
                    raise ValueError(
                        f"Question trigger_types must be a list of strings: {bank_path}"
                    )
                if trigger_type not in trigger_types:
                    continue
            question["prompt"] = str(question.pop("template")).format_map(values)
            question["hazard_family"] = hazard_family
            question["question_bank_scope"] = (
                "general" if bank_path == general_path else "hazard_specific"
            )
            question["ground_truth_source"] = trigger["source"]
            question["ground_truth_source_id"] = trigger["source_id"]
            questions.append(question)

    ids = [question.get("question_id") for question in questions]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("Question IDs must exist and be unique across selected banks")
    if not questions:
        raise ValueError(
            f"No questions apply to trigger type {trigger_type!r} in {bank_dir}"
        )
    return questions, bank_paths
