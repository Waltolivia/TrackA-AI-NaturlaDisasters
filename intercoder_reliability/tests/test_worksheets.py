import csv
import json
from pathlib import Path

import pytest

from intercoder_reliability.rubric import load_rubric
from intercoder_reliability.worksheets import (
    BLIND_MAP_FILENAME,
    NOTES_COLUMN,
    UNITS_FILENAME,
    coder_sheet_path,
    collect_units,
    extract_units,
    load_units,
    read_sheet,
    unit_id_for,
    write_workspace,
)


def shipped_rubric():
    return load_rubric(Path(__file__).parents[1] / "config" / "rubric.study-v3.json")


def sample_responses(cycle_id: str = "MSG-1") -> dict:
    return {
        "schema_version": "1.1",
        "cycle_id": cycle_id,
        "event_id": "EVT-00000001",
        "message_id": "MSG-1",
        "action": "NEW_EVENT",
        "hazard_family": "flood",
        "study_conditions": ["search-on"],
        "event": "Flash Flood Warning",
        "area": "Salt Lake County, Utah",
        "source": "NWS",
        "source_id": "alert-1",
        "source_timestamp": "2026-10-01T00:00:00Z",
        "responses": [
            {
                "provider": "openai",
                "target_id": "openai-search",
                "requested_model": "gpt-test",
                "resolved_model": "gpt-test",
                "question_id": "q1",
                "category": "situational",
                "prompt": "Prompt one",
                "response": "Answer one",
                "citations": [{"url": "https://www.weather.gov/x"}],
                "search_requested": True,
                "search_used": True,
                "search_count": 1,
            },
            {
                "provider": "anthropic",
                "target_id": "anthropic-search",
                "question_id": "q2",
                "category": "protective-action",
                "prompt": "Prompt two",
                "response": "Answer two",
                "citations": [],
                "search_requested": True,
                "search_used": False,
                "search_count": 0,
            },
            {
                "provider": "google",
                "target_id": "google-search",
                "question_id": "q3",
                "response": "   ",
            },
        ],
    }


def write_responses(tmp_path: Path, payload: dict, name: str = "responses.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_extract_units_skips_empty_answers_and_hides_provider(tmp_path: Path) -> None:
    path = write_responses(tmp_path, sample_responses())
    units, blind_map = extract_units(path)

    assert len(units) == 2
    assert {unit["question_id"] for unit in units} == {"q1", "q2"}
    for unit in units:
        assert "provider" not in unit
        assert "target_id" not in unit
    assert blind_map[units[0]["unit_id"]]["provider"] == "openai"
    assert blind_map[units[1]["unit_id"]]["provider"] == "anthropic"
    assert units[0]["citations"] == [{"url": "https://www.weather.gov/x"}]
    assert units[0]["ground_truth_ref"] is None


def test_extract_units_requires_cycle_id(tmp_path: Path) -> None:
    payload = sample_responses()
    del payload["cycle_id"]
    path = write_responses(tmp_path, payload)
    with pytest.raises(ValueError, match="cycle_id"):
        extract_units(path)


def test_unit_id_is_stable_and_sensitive_to_every_input() -> None:
    base = unit_id_for("MSG-1", "openai-search", "q1")
    assert base == unit_id_for("MSG-1", "openai-search", "q1")
    assert base.startswith("U-")
    assert base != unit_id_for("MSG-2", "openai-search", "q1")
    assert base != unit_id_for("MSG-1", "anthropic-search", "q1")
    assert base != unit_id_for("MSG-1", "openai-search", "q2")


def test_collect_units_deduplicates_convenience_copies(tmp_path: Path) -> None:
    path = write_responses(tmp_path, sample_responses())
    units, blind_map, stats = collect_units([path, path])
    assert len(units) == 2
    assert len(blind_map) == 2
    assert stats == {"responses_files": 2, "units": 2, "duplicate_units": 2}
    assert [unit["unit_id"] for unit in units] == sorted(
        unit["unit_id"] for unit in units
    )


def test_ground_truth_reference_is_detected(tmp_path: Path) -> None:
    ai_dir = tmp_path / "EVT-00000001" / "EVT-00000001_AI"
    ai_dir.mkdir(parents=True)
    (tmp_path / "EVT-00000001" / "EVT-00000001_weather").mkdir()
    path = ai_dir / "responses.json"
    path.write_text(json.dumps(sample_responses()), encoding="utf-8")

    units, _ = extract_units(path)
    assert units[0]["ground_truth_ref"] == str(
        tmp_path / "EVT-00000001" / "EVT-00000001_weather"
    )


def test_write_workspace_creates_blind_workspace(tmp_path: Path) -> None:
    rubric = shipped_rubric()
    path = write_responses(tmp_path, sample_responses())
    units, blind_map, _ = collect_units([path])
    output = tmp_path / "coding"

    result = write_workspace(
        units=units, blind_map=blind_map, output_dir=output, rubric=rubric
    )

    assert result["unit_count"] == 2
    assert Path(result["units_file"]).is_file()
    assert (output / BLIND_MAP_FILENAME).is_file()
    assert load_units(output / UNITS_FILENAME) == units

    blind_payload = json.loads((output / BLIND_MAP_FILENAME).read_text(encoding="utf-8"))
    assert "Do not share" in blind_payload["warning"]
    assert set(blind_payload["units"]) == {unit["unit_id"] for unit in units}

    sheet = coder_sheet_path(output, "a")
    with sheet.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    assert header == ["unit_id", *rubric.dimension_ids, NOTES_COLUMN]
    assert [row[0] for row in rows] == [unit["unit_id"] for unit in units]
    assert all(cell == "" for row in rows for cell in row[1:])


def test_write_workspace_refuses_to_overwrite_without_flag(tmp_path: Path) -> None:
    rubric = shipped_rubric()
    path = write_responses(tmp_path, sample_responses())
    units, blind_map, _ = collect_units([path])
    output = tmp_path / "coding"
    write_workspace(units=units, blind_map=blind_map, output_dir=output, rubric=rubric)

    with pytest.raises(FileExistsError):
        write_workspace(
            units=units, blind_map=blind_map, output_dir=output, rubric=rubric
        )
    write_workspace(
        units=units,
        blind_map=blind_map,
        output_dir=output,
        rubric=rubric,
        overwrite=True,
    )


def test_read_sheet_reports_problems(tmp_path: Path) -> None:
    rubric = shipped_rubric()
    dimensions = rubric.dimension_ids
    sheet = tmp_path / "coder-a.csv"
    header = ["unit_id", *dimensions, NOTES_COLUMN]
    good = ["U-aaaaaaaaaaaa", *(["2"] * len(dimensions)), ""]
    out_of_range = ["U-bbbbbbbbbbbb", "9", *(["1"] * (len(dimensions) - 1)), ""]
    not_integer = ["U-cccccccccccc", "x", *(["1"] * (len(dimensions) - 1)), ""]
    with sheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerow(good)
        writer.writerow(out_of_range)
        writer.writerow(not_integer)
        writer.writerow(good)

    scores, problems = read_sheet(sheet, rubric)

    assert len(scores) == 3
    assert scores["U-aaaaaaaaaaaa"]["safety"] == 2
    assert scores["U-bbbbbbbbbbbb"][dimensions[0]] is None
    assert scores["U-cccccccccccc"][dimensions[0]] is None
    joined = " | ".join(problems)
    assert "outside" in joined
    assert "not an integer" in joined
    assert "duplicates unit_id" in joined


def test_read_sheet_requires_rubric_columns(tmp_path: Path) -> None:
    rubric = shipped_rubric()
    sheet = tmp_path / "coder-a.csv"
    sheet.write_text("unit_id,notes\nU-1,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing rubric columns"):
        read_sheet(sheet, rubric)
