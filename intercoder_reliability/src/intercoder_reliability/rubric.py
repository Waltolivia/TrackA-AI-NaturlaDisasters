from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RUBRIC_FILENAME = "rubric.study-v3.json"


@dataclass(frozen=True)
class Dimension:
    """One scored rubric dimension."""

    dimension_id: str
    label: str
    description: str
    anchors: dict[str, str]


@dataclass(frozen=True)
class Rubric:
    """A frozen, versioned coding rubric."""

    rubric_id: str
    minimum: int
    maximum: int
    dimensions: tuple[Dimension, ...]

    @property
    def dimension_ids(self) -> list[str]:
        return [dimension.dimension_id for dimension in self.dimensions]

    @property
    def valid_scores(self) -> list[int]:
        return list(range(self.minimum, self.maximum + 1))

    def dimension(self, dimension_id: str) -> Dimension:
        for dimension in self.dimensions:
            if dimension.dimension_id == dimension_id:
                return dimension
        raise KeyError(dimension_id)


def default_rubric_path() -> Path:
    """Return the rubric shipped beside this module, falling back to the module config dir."""

    module_root = Path(__file__).resolve().parents[2]
    candidate = module_root / "config" / DEFAULT_RUBRIC_FILENAME
    if candidate.is_file():
        return candidate
    return Path("config") / DEFAULT_RUBRIC_FILENAME


def load_rubric(path: Path) -> Rubric:
    """Load and validate a rubric JSON file."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Rubric file must contain one JSON object")
    rubric_id = data.get("rubric_id")
    if not isinstance(rubric_id, str) or not rubric_id.strip():
        raise ValueError("Rubric 'rubric_id' must be a non-empty string")
    scale = data.get("scale")
    if not isinstance(scale, dict):
        raise ValueError("Rubric 'scale' must be an object")
    minimum = scale.get("minimum")
    maximum = scale.get("maximum")
    if not isinstance(minimum, int) or not isinstance(maximum, int):
        raise ValueError("Rubric scale 'minimum' and 'maximum' must be integers")
    if minimum >= maximum:
        raise ValueError("Rubric scale 'minimum' must be less than 'maximum'")
    raw_dimensions = data.get("dimensions")
    if not isinstance(raw_dimensions, list) or not raw_dimensions:
        raise ValueError("Rubric 'dimensions' must be a non-empty list")

    dimensions: list[Dimension] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_dimensions):
        if not isinstance(raw, dict):
            raise ValueError(f"Rubric dimension {index} must be an object")
        dimension_id = raw.get("dimension_id")
        if not isinstance(dimension_id, str) or not dimension_id.strip():
            raise ValueError(
                f"Rubric dimension {index} needs a non-empty 'dimension_id'"
            )
        if dimension_id in seen:
            raise ValueError(f"Duplicate rubric dimension_id: {dimension_id}")
        seen.add(dimension_id)
        anchors = raw.get("anchors") or {}
        if not isinstance(anchors, dict):
            raise ValueError(
                f"Rubric dimension {dimension_id} 'anchors' must be an object"
            )
        for score in range(minimum, maximum + 1):
            anchor = anchors.get(str(score))
            if not isinstance(anchor, str) or not anchor.strip():
                raise ValueError(
                    f"Rubric dimension {dimension_id} is missing an anchor for score {score}"
                )
        dimensions.append(
            Dimension(
                dimension_id=dimension_id,
                label=str(raw.get("label") or dimension_id),
                description=str(raw.get("description") or ""),
                anchors={str(key): str(value) for key, value in anchors.items()},
            )
        )
    return Rubric(
        rubric_id=rubric_id,
        minimum=minimum,
        maximum=maximum,
        dimensions=tuple(dimensions),
    )
