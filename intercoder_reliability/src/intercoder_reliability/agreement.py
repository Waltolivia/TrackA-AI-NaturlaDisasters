from __future__ import annotations

from typing import Sequence

LEVELS = ("nominal", "ordinal", "interval")
_UNDEFINED_TOLERANCE = 1e-12


def percent_agreement(pairs: Sequence[tuple[int, int]]) -> float | None:
    """Exact agreement proportion for paired scores, or None when there are none."""

    if not pairs:
        return None
    matches = sum(1 for first, second in pairs if first == second)
    return matches / len(pairs)


def cohen_kappa(
    pairs: Sequence[tuple[int, int]],
    *,
    categories: Sequence[int],
    weights: str = "unweighted",
) -> float | None:
    """Cohen's kappa for two coders on one dimension.

    ``weights`` is ``unweighted``, ``linear``, or ``quadratic``. Returns None when
    the statistic is undefined (no pairs, a single category, or no chance variance).
    """

    if not pairs:
        return None
    categories = list(categories)
    size = len(categories)
    if size < 2:
        return None
    index = {value: position for position, value in enumerate(categories)}
    observed = [[0] * size for _ in range(size)]
    for first, second in pairs:
        observed[index[first]][index[second]] += 1
    total = len(pairs)
    row_totals = [sum(row) for row in observed]
    column_totals = [
        sum(observed[row][column] for row in range(size)) for column in range(size)
    ]

    if weights == "unweighted":
        agreement = sum(observed[i][i] for i in range(size)) / total
        expected = (
            sum(row_totals[i] * column_totals[i] for i in range(size)) / (total * total)
        )
    elif weights in {"linear", "quadratic"}:
        span = size - 1
        agreement = 0.0
        expected = 0.0
        for i in range(size):
            for j in range(size):
                difference = abs(i - j) / span
                weight = 1.0 - (difference if weights == "linear" else difference**2)
                agreement += observed[i][j] * weight
                expected += row_totals[i] * column_totals[j] * weight
        agreement /= total
        expected /= total * total
    else:
        raise ValueError(f"Unknown weights: {weights}")

    if 1.0 - expected <= _UNDEFINED_TOLERANCE:
        return None
    return (agreement - expected) / (1.0 - expected)


def krippendorff_alpha(
    units: Sequence[Sequence[int]],
    *,
    level: str = "ordinal",
    categories: Sequence[int],
) -> float | None:
    """Krippendorff's alpha for any number of coders (two or more values per unit).

    ``level`` selects the difference function: ``nominal``, ``ordinal``, or
    ``interval``. Units with fewer than two scores are not pairable and are
    ignored, which is the standard treatment of missing data.
    """

    if level not in LEVELS:
        raise ValueError(f"Unknown level: {level}")
    categories = list(categories)
    size = len(categories)
    index = {value: position for position, value in enumerate(categories)}
    pairable = [list(unit) for unit in units if len(unit) >= 2]
    total = sum(len(unit) for unit in pairable)
    if total < 2 or size < 2:
        return None

    coincidence = [[0.0] * size for _ in range(size)]
    for unit in pairable:
        count = len(unit)
        for position, value in enumerate(unit):
            others = count - 1
            for other in unit[:position] + unit[position + 1 :]:
                coincidence[index[value]][index[other]] += 1.0 / others
    marginals = [sum(row) for row in coincidence]

    def difference(first: int, second: int) -> float:
        if level == "nominal":
            return 0.0 if first == second else 1.0
        if level == "interval":
            return float((first - second) ** 2)
        low, high = sorted((index[first], index[second]))
        between = sum(marginals[position] for position in range(low, high + 1))
        return (between - (marginals[low] + marginals[high]) / 2.0) ** 2

    observed = 0.0
    expected = 0.0
    for i in range(size):
        for j in range(size):
            distance = difference(categories[i], categories[j])
            observed += coincidence[i][j] * distance
            expected += marginals[i] * marginals[j] * distance
    observed /= total
    expected /= total * (total - 1)
    if expected <= 0:
        return None
    return 1.0 - observed / expected
