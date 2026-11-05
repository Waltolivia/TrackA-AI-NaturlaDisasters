import csv
import json
from pathlib import Path

import pytest

from intercoder_reliability import cli
from intercoder_reliability.rubric import load_rubric
from intercoder_reliability.worksheets import load_units

RUBRIC_PATH = Path(__file__).parents[1] / "config" / "rubric.study-v3.json"
TARGETS = (
    ("openai", "openai-search"),
    ("anthropic", "anthropic-search"),
    ("google", "google-search"),
)


def shipped_rubric():
    return load_rubric(RUBRIC_PATH)


def ai_payload() -> dict:
    responses = []
    for provider, target_id in TARGETS:
        for question_id, category in (
            ("q1", "situational"),
            ("q2", "protective-action"),
        ):
            responses.append(
                {
                    "provider": provider,
                    "target_id": target_id,
                    "requested_model": f"{provider}-model",
                    "resolved_model": f"{provider}-model",
                    "question_id": question_id,
                    "category": category,
                    "prompt": f"Prompt {question_id} for {provider}",
                    "response": f"Answer from {provider} for {question_id}",
                    "citations": [{"url": "https://www.weather.gov/"}],
                    "search_requested": True,
                    "search_used": True,
                    "search_count": 1,
                }
            )
    return {
        "schema_version": "1.1",
        "cycle_id": "MSG-1",
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
        "completed_probe_count": 6,
        "failed_probe_count": 0,
        "responses": responses,
    }


def build_results_tree(tmp_path: Path) -> Path:
    """A realistic EVT folder with a weather sibling, a run folder, and a convenience copy."""

    event = tmp_path / "results" / "2026" / "October" / "Sep_28-Oct_04" / "EVT-00000001"
    ai_dir = event / "EVT-00000001_AI"
    run_dir = ai_dir / "runs" / "MSG-1"
    run_dir.mkdir(parents=True)
    (event / "EVT-00000001_weather").mkdir()
    payload = json.dumps(ai_payload(), indent=2)
    (run_dir / "responses.json").write_text(payload, encoding="utf-8")
    (ai_dir / "responses.json").write_text(payload, encoding="utf-8")
    return tmp_path / "results"


def fill_sheets(workspace: Path, mismatch_index: int = 5) -> list[str]:
    """Coder A and B agree except one safety score on one unit."""

    rubric = shipped_rubric()
    unit_ids = [unit["unit_id"] for unit in load_units(workspace / "units.jsonl")]
    values = [0, 1, 2, 0, 1, 2]
    safety_offset = 1 + rubric.dimension_ids.index("safety")
    for coder in ("a", "b"):
        path = workspace / f"coder-{coder}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["unit_id", *rubric.dimension_ids, "notes"])
            for index, unit_id in enumerate(unit_ids):
                row = [unit_id] + [values[index]] * len(rubric.dimension_ids) + [""]
                if coder == "b" and index == mismatch_index:
                    row[safety_offset] = 1 if values[index] != 1 else 2
                writer.writerow(row)
    return unit_ids


def test_export_creates_blind_workspace(tmp_path: Path) -> None:
    results = build_results_tree(tmp_path)
    workspace = tmp_path / "coding"

    code = cli.main(
        [
            "--rubric",
            str(RUBRIC_PATH),
            "export",
            "--results-root",
            str(results),
            "--output",
            str(workspace),
        ]
    )

    assert code == 0
    for name in ("units.jsonl", "blind_map.json", "coder-a.csv", "coder-b.csv"):
        assert (workspace / name).is_file()
    units = load_units(workspace / "units.jsonl")
    assert len(units) == 6
    assert all("provider" not in unit for unit in units)
    blind = json.loads((workspace / "blind_map.json").read_text(encoding="utf-8"))
    assert len(blind["units"]) == 6
    assert {entry["provider"] for entry in blind["units"].values()} == {
        "openai",
        "anthropic",
        "google",
    }


def test_export_without_a_source_fails(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--rubric",
                str(RUBRIC_PATH),
                "export",
                "--output",
                str(tmp_path / "coding"),
            ]
        )


def test_validate_and_reliability_end_to_end(tmp_path: Path) -> None:
    results = build_results_tree(tmp_path)
    workspace = tmp_path / "coding"
    assert (
        cli.main(
            [
                "--rubric",
                str(RUBRIC_PATH),
                "export",
                "--results-root",
                str(results),
                "--output",
                str(workspace),
            ]
        )
        == 0
    )
    assert len(fill_sheets(workspace)) == 6

    assert (
        cli.main(
            ["--rubric", str(RUBRIC_PATH), "validate", "--workspace", str(workspace)]
        )
        == 0
    )
    assert (
        cli.main(
            ["--rubric", str(RUBRIC_PATH), "reliability", "--workspace", str(workspace)]
        )
        == 0
    )

    report = json.loads(
        (workspace / "reliability-report.json").read_text(encoding="utf-8")
    )
    assert report["counts"]["common_units"] == 6
    assert len(report["dimensions"]) == 7
    assert report["overall"]["percent_agreement"] == pytest.approx((6 + 5 / 6) / 7)
    assert report["overall"]["cohen_kappa"] == pytest.approx((6 * 1.0 + 0.75) / 7)

    safety = next(
        dimension
        for dimension in report["dimensions"]
        if dimension["dimension_id"] == "safety"
    )
    assert safety["percent_agreement"] == pytest.approx(5 / 6)
    assert safety["cohen_kappa"] == pytest.approx(0.75)
    assert len(safety["disagreements"]) == 1
    assert "provider" not in safety["disagreements"][0]


def test_validate_flags_incomplete_sheet(tmp_path: Path) -> None:
    results = build_results_tree(tmp_path)
    workspace = tmp_path / "coding"
    cli.main(
        [
            "--rubric",
            str(RUBRIC_PATH),
            "export",
            "--results-root",
            str(results),
            "--output",
            str(workspace),
        ]
    )
    fill_sheets(workspace)

    sheet = workspace / "coder-a.csv"
    lines = sheet.read_text(encoding="utf-8").splitlines()
    cells = lines[1].split(",")
    cells[1] = ""
    lines[1] = ",".join(cells)
    sheet.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code = cli.main(
        ["--rubric", str(RUBRIC_PATH), "validate", "--workspace", str(workspace)]
    )
    assert code == 1


def test_reliability_reveal_attaches_provider_and_consensus(tmp_path: Path) -> None:
    results = build_results_tree(tmp_path)
    workspace = tmp_path / "coding"
    cli.main(
        [
            "--rubric",
            str(RUBRIC_PATH),
            "export",
            "--results-root",
            str(results),
            "--output",
            str(workspace),
        ]
    )
    fill_sheets(workspace)

    code = cli.main(
        [
            "--rubric",
            str(RUBRIC_PATH),
            "reliability",
            "--workspace",
            str(workspace),
            "--reveal",
            "--consensus",
            str(workspace / "coder-a.csv"),
        ]
    )
    assert code == 0

    report = json.loads(
        (workspace / "reliability-report.json").read_text(encoding="utf-8")
    )
    safety = next(
        dimension
        for dimension in report["dimensions"]
        if dimension["dimension_id"] == "safety"
    )
    assert safety["disagreements"][0]["provider"] in {
        "openai",
        "anthropic",
        "google",
    }
    consensus = report["consensus"]
    assert consensus["coder_a_vs_consensus"]["overall"]["cohen_kappa"] == pytest.approx(
        1.0
    )
    assert consensus["coder_b_vs_consensus"]["overall"]["cohen_kappa"] == pytest.approx(
        (6 * 1.0 + 0.75) / 7
    )
