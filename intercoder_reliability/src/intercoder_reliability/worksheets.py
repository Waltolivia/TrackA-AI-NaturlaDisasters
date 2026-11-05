from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .rubric import Rubric

UNIT_SCHEMA_VERSION = "1.0"
BLIND_MAP_SCHEMA_VERSION = "1.0"
UNITS_FILENAME = "units.jsonl"
BLIND_MAP_FILENAME = "blind_map.json"
NOTES_COLUMN = "notes"
DEFAULT_CODERS = ("a", "b")
BLIND_MAP_WARNING = (
    "Private key file. Do not share it with coders; it reveals which provider "
    "produced each blind unit and would break blinding."
)


def unit_id_for(cycle_id: str, target_id: str, question_id: str) -> str:
    """Return a stable, provider-blind identifier for one scored response."""

    digest = hashlib.sha256(
        f"{cycle_id}\x1f{target_id}\x1f{question_id}".encode("utf-8")
    ).hexdigest()
    return f"U-{digest[:12]}"


def coder_sheet_path(output_dir: Path, coder: str) -> Path:
    return Path(output_dir) / f"coder-{coder}.csv"


def discover_responses_files(results_root: Path) -> list[Path]:
    """Return every responses.json beneath a results root, sorted for determinism."""

    return sorted(Path(results_root).rglob("responses.json"))


def extract_units(
    responses_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Read one responses.json into blind coding units plus a private blind map.

    Probes without response text (provider errors or empty answers) are not
    codable and are skipped; their raw records remain in the AI archive.
    """

    responses_path = Path(responses_path)
    data = json.loads(responses_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{responses_path} must contain one JSON object")
    cycle_id = str(data.get("cycle_id") or "")
    if not cycle_id:
        raise ValueError(f"{responses_path} is missing 'cycle_id'")
    ground_truth_ref = _ground_truth_reference(responses_path)

    units: list[dict[str, Any]] = []
    blind_map: dict[str, dict[str, Any]] = {}
    for response in data.get("responses") or []:
        if not isinstance(response, dict):
            continue
        answer = str(response.get("response") or "").strip()
        if not answer:
            continue
        target_id = str(response.get("target_id") or "")
        question_id = str(response.get("question_id") or "")
        if not target_id or not question_id:
            continue
        unit_id = unit_id_for(cycle_id, target_id, question_id)
        units.append(
            {
                "schema_version": UNIT_SCHEMA_VERSION,
                "unit_id": unit_id,
                "cycle_id": cycle_id,
                "event_id": data.get("event_id"),
                "message_id": data.get("message_id"),
                "action": data.get("action"),
                "hazard_family": data.get("hazard_family"),
                "study_conditions": data.get("study_conditions") or [],
                "event": data.get("event"),
                "area": data.get("area"),
                "source": data.get("source"),
                "source_id": data.get("source_id"),
                "source_timestamp": data.get("source_timestamp"),
                "question_id": question_id,
                "category": response.get("category"),
                "prompt": response.get("prompt"),
                "response": answer,
                "citations": response.get("citations") or [],
                "search_requested": response.get("search_requested"),
                "search_used": response.get("search_used"),
                "search_count": response.get("search_count"),
                "ground_truth_ref": ground_truth_ref,
            }
        )
        blind_map[unit_id] = {
            "cycle_id": cycle_id,
            "event_id": data.get("event_id"),
            "message_id": data.get("message_id"),
            "target_id": target_id,
            "question_id": question_id,
            "provider": response.get("provider"),
            "requested_model": response.get("requested_model"),
            "resolved_model": response.get("resolved_model"),
            "source_file": str(responses_path),
        }
    return units, blind_map


def collect_units(
    responses_paths: list[Path],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, int]]:
    """Merge many responses.json files, de-duplicating convenience copies."""

    units_by_id: dict[str, dict[str, Any]] = {}
    blind_map: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for path in responses_paths:
        units, mapping = extract_units(path)
        for unit in units:
            unit_id = unit["unit_id"]
            if unit_id in units_by_id:
                # The convenience responses.json directly under EVT-..._AI/ is a
                # copy of the latest runs/MSG-.../ file, so the unit repeats.
                duplicates += 1
                continue
            units_by_id[unit_id] = unit
            blind_map[unit_id] = mapping[unit_id]
    ordered = [units_by_id[unit_id] for unit_id in sorted(units_by_id)]
    stats = {
        "responses_files": len(responses_paths),
        "units": len(ordered),
        "duplicate_units": duplicates,
    }
    return ordered, blind_map, stats


def write_workspace(
    *,
    units: list[dict[str, Any]],
    blind_map: dict[str, dict[str, Any]],
    output_dir: Path,
    rubric: Rubric,
    coders: tuple[str, ...] = DEFAULT_CODERS,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write blind units, the private blind map, and blank coder sheets."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    units_path = output_dir / UNITS_FILENAME
    blind_path = output_dir / BLIND_MAP_FILENAME
    if not overwrite:
        for path in (units_path, blind_path):
            if path.exists():
                raise FileExistsError(
                    f"{path} already exists; pass --overwrite to replace the workspace"
                )
    _write_units(units_path, units)
    _write_json(
        blind_path,
        {
            "schema_version": BLIND_MAP_SCHEMA_VERSION,
            "warning": BLIND_MAP_WARNING,
            "units": blind_map,
        },
    )
    sheet_paths: dict[str, str] = {}
    for coder in coders:
        path = coder_sheet_path(output_dir, coder)
        _write_sheet_template(path, units, rubric)
        sheet_paths[coder] = str(path)
    return {
        "output_dir": str(output_dir),
        "units_file": str(units_path),
        "blind_map_file": str(blind_path),
        "coder_sheets": sheet_paths,
        "unit_count": len(units),
    }


def load_units(path: Path) -> list[dict[str, Any]]:
    """Read a units.jsonl file."""

    units: list[dict[str, Any]] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            unit = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in {path} at line {line_number}: {exc}"
            ) from exc
        if not isinstance(unit, dict) or not unit.get("unit_id"):
            raise ValueError(f"{path}:{line_number} is not a coding unit object")
        units.append(unit)
    return units


def read_sheet(
    path: Path, rubric: Rubric
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Read one filled coder sheet into ``unit_id -> scores`` plus a problem list."""

    path = Path(path)
    problems: list[str] = []
    scores: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "unit_id" not in fieldnames:
            raise ValueError(f"{path} is missing the 'unit_id' column")
        missing_columns = [
            dimension_id
            for dimension_id in rubric.dimension_ids
            if dimension_id not in fieldnames
        ]
        if missing_columns:
            raise ValueError(
                f"{path} is missing rubric columns: {', '.join(missing_columns)}"
            )
        seen: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            unit_id = (row.get("unit_id") or "").strip()
            if not unit_id:
                problems.append(f"{path}:{line_number} has no unit_id")
                continue
            if unit_id in seen:
                problems.append(f"{path}:{line_number} duplicates unit_id {unit_id}")
                continue
            seen.add(unit_id)
            entry: dict[str, Any] = {}
            for dimension_id in rubric.dimension_ids:
                raw = (row.get(dimension_id) or "").strip()
                if raw == "":
                    entry[dimension_id] = None
                    continue
                try:
                    value = int(raw)
                except ValueError:
                    problems.append(
                        f"{path}:{line_number} {dimension_id}='{raw}' is not an integer"
                    )
                    entry[dimension_id] = None
                    continue
                if not rubric.minimum <= value <= rubric.maximum:
                    problems.append(
                        f"{path}:{line_number} {dimension_id}={value} is outside "
                        f"{rubric.minimum}-{rubric.maximum}"
                    )
                    entry[dimension_id] = None
                    continue
                entry[dimension_id] = value
            entry[NOTES_COLUMN] = (row.get(NOTES_COLUMN) or "").strip()
            scores[unit_id] = entry
    return scores, problems


def _write_units(path: Path, units: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for unit in units:
            handle.write(json.dumps(unit, ensure_ascii=False, sort_keys=True) + "\n")


def _write_sheet_template(path: Path, units: list[dict[str, Any]], rubric: Rubric) -> None:
    fieldnames = ["unit_id", *rubric.dimension_ids, NOTES_COLUMN]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for unit in units:
            row = {name: "" for name in fieldnames}
            row["unit_id"] = unit["unit_id"]
            writer.writerow(row)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _ground_truth_reference(responses_path: Path) -> str | None:
    """Return the adjacent EVT-..._weather folder, if this cycle has one."""

    current = responses_path.parent
    for _ in range(4):
        if current.name.endswith("_AI"):
            event_dir = current.parent
            weather = event_dir / f"{event_dir.name}_weather"
            if weather.is_dir():
                return str(weather)
            return None
        current = current.parent
    return None
