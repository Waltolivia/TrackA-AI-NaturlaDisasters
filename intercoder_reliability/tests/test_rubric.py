import json
from pathlib import Path

import pytest

from intercoder_reliability.rubric import (
    Rubric,
    default_rubric_path,
    load_rubric,
)

EXPECTED_DIMENSIONS = [
    "factual_consistency",
    "ground_truth_match",
    "official_source_referral",
    "protective_action",
    "temporal_freshness",
    "uncertainty_calibration",
    "safety",
]


def shipped_rubric_path() -> Path:
    return Path(__file__).parents[1] / "config" / "rubric.study-v3.json"


def test_default_rubric_path_points_at_the_shipped_rubric() -> None:
    path = default_rubric_path()
    assert path.is_file()
    assert path.name == "rubric.study-v3.json"


def test_shipped_rubric_is_complete() -> None:
    rubric = load_rubric(shipped_rubric_path())
    assert isinstance(rubric, Rubric)
    assert rubric.rubric_id == "study-v3"
    assert (rubric.minimum, rubric.maximum) == (0, 2)
    assert rubric.valid_scores == [0, 1, 2]
    assert rubric.dimension_ids == EXPECTED_DIMENSIONS
    for dimension in rubric.dimensions:
        assert dimension.label
        for score in ("0", "1", "2"):
            assert dimension.anchors[score].strip()


def test_dimension_lookup_raises_for_unknown_id() -> None:
    rubric = load_rubric(shipped_rubric_path())
    with pytest.raises(KeyError):
        rubric.dimension("not-a-dimension")


def write_rubric(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def base_rubric() -> dict:
    return {
        "rubric_id": "test",
        "scale": {"minimum": 0, "maximum": 2},
        "dimensions": [
            {
                "dimension_id": "safety",
                "label": "Safety",
                "anchors": {"0": "harmful", "1": "mixed", "2": "safe"},
            }
        ],
    }


def test_missing_anchor_is_rejected(tmp_path: Path) -> None:
    payload = base_rubric()
    del payload["dimensions"][0]["anchors"]["1"]
    with pytest.raises(ValueError, match="anchor for score 1"):
        load_rubric(write_rubric(tmp_path, payload))


def test_duplicate_dimension_ids_are_rejected(tmp_path: Path) -> None:
    payload = base_rubric()
    payload["dimensions"].append(dict(payload["dimensions"][0]))
    with pytest.raises(ValueError, match="Duplicate rubric dimension_id"):
        load_rubric(write_rubric(tmp_path, payload))


def test_bad_scale_is_rejected(tmp_path: Path) -> None:
    payload = base_rubric()
    payload["scale"] = {"minimum": 2, "maximum": 2}
    with pytest.raises(ValueError, match="less than"):
        load_rubric(write_rubric(tmp_path, payload))


def test_non_object_rubric_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one JSON object"):
        load_rubric(write_rubric(tmp_path, [1, 2, 3]))
