from __future__ import annotations

from typing import Any

from .agreement import cohen_kappa, krippendorff_alpha, percent_agreement
from .rubric import Rubric


def compute_reliability(
    *,
    rubric: Rubric,
    coder_a: dict[str, dict[str, Any]],
    coder_b: dict[str, dict[str, Any]],
    blind_map: dict[str, dict[str, Any]] | None = None,
    include_disagreements: bool = True,
) -> dict[str, Any]:
    """Compare two coders per rubric dimension and overall.

    Only units scored by both coders contribute to a dimension, which is the
    standard pairwise-deletion treatment of incomplete coding.
    """

    common_units = sorted(set(coder_a) & set(coder_b))
    dimensions: list[dict[str, Any]] = []
    for dimension_id in rubric.dimension_ids:
        pairs: list[tuple[int, int]] = []
        disagreements: list[dict[str, Any]] = []
        missing = 0
        for unit_id in common_units:
            first = coder_a[unit_id].get(dimension_id)
            second = coder_b[unit_id].get(dimension_id)
            if first is None or second is None:
                missing += 1
                continue
            pairs.append((first, second))
            if first != second and include_disagreements:
                record: dict[str, Any] = {
                    "unit_id": unit_id,
                    "coder_a": first,
                    "coder_b": second,
                }
                if blind_map:
                    reference = blind_map.get(unit_id) or {}
                    record["provider"] = reference.get("provider")
                    record["target_id"] = reference.get("target_id")
                    record["event_id"] = reference.get("event_id")
                disagreements.append(record)
        dimensions.append(
            {
                "dimension_id": dimension_id,
                "label": rubric.dimension(dimension_id).label,
                "paired_units": len(pairs),
                "missing_units": missing,
                "percent_agreement": percent_agreement(pairs),
                "cohen_kappa": cohen_kappa(pairs, categories=rubric.valid_scores),
                "cohen_kappa_quadratic": cohen_kappa(
                    pairs, categories=rubric.valid_scores, weights="quadratic"
                ),
                "krippendorff_alpha_ordinal": krippendorff_alpha(
                    [[first, second] for first, second in pairs],
                    level="ordinal",
                    categories=rubric.valid_scores,
                ),
                "disagreements": disagreements,
            }
        )

    overall = {
        "percent_agreement": _mean(
            [dimension["percent_agreement"] for dimension in dimensions]
        ),
        "cohen_kappa": _mean([dimension["cohen_kappa"] for dimension in dimensions]),
        "cohen_kappa_quadratic": _mean(
            [dimension["cohen_kappa_quadratic"] for dimension in dimensions]
        ),
        "krippendorff_alpha_ordinal": _mean(
            [dimension["krippendorff_alpha_ordinal"] for dimension in dimensions]
        ),
    }
    return {
        "rubric": {
            "rubric_id": rubric.rubric_id,
            "minimum": rubric.minimum,
            "maximum": rubric.maximum,
            "dimension_ids": rubric.dimension_ids,
        },
        "counts": {
            "coder_a_units": len(coder_a),
            "coder_b_units": len(coder_b),
            "common_units": len(common_units),
            "only_coder_a": sorted(set(coder_a) - set(coder_b)),
            "only_coder_b": sorted(set(coder_b) - set(coder_a)),
        },
        "overall": overall,
        "dimensions": dimensions,
    }


def _mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _format_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_text_report(report: dict[str, Any]) -> str:
    """Render a readable agreement table from a reliability report."""

    rubric = report.get("rubric", {})
    lines = [
        "Intercoder reliability report",
        f"Rubric: {rubric.get('rubric_id', 'n/a')} "
        f"(scale {rubric.get('minimum', '?')}-{rubric.get('maximum', '?')})",
        f"Coder A: {report.get('coder_a', {}).get('sheet', 'n/a')}",
        f"Coder B: {report.get('coder_b', {}).get('sheet', 'n/a')}",
        f"Common units: {report.get('counts', {}).get('common_units', 0)}",
        "",
        f"{'Dimension':<26}{'n':>5}{'miss':>6}{'agree%':>9}"
        f"{'kappa':>9}{'kappa_q':>9}{'alpha_ord':>11}",
    ]
    for dimension in report.get("dimensions", []):
        lines.append(
            f"{dimension['dimension_id']:<26}"
            f"{dimension['paired_units']:>5}"
            f"{dimension['missing_units']:>6}"
            f"{_format_percent(dimension.get('percent_agreement')):>9}"
            f"{_format_number(dimension.get('cohen_kappa')):>9}"
            f"{_format_number(dimension.get('cohen_kappa_quadratic')):>9}"
            f"{_format_number(dimension.get('krippendorff_alpha_ordinal')):>11}"
        )
    overall = report.get("overall", {})
    lines.append(
        f"{'MEAN over dimensions':<26}{'':>5}{'':>6}"
        f"{_format_percent(overall.get('percent_agreement')):>9}"
        f"{_format_number(overall.get('cohen_kappa')):>9}"
        f"{_format_number(overall.get('cohen_kappa_quadratic')):>9}"
        f"{_format_number(overall.get('krippendorff_alpha_ordinal')):>11}"
    )
    lines.append("")
    lines.append(
        "kappa = Cohen's kappa; kappa_q = quadratic-weighted kappa; "
        "alpha_ord = ordinal Krippendorff's alpha."
    )
    lines.append(
        "n/a means the statistic is undefined: no paired scores or no chance variance."
    )

    consensus = report.get("consensus")
    if consensus:
        lines.append("")
        lines.append(f"Consensus sheet: {consensus.get('sheet', 'n/a')}")
        for key, label in (
            ("coder_a_vs_consensus", "Coder A vs consensus"),
            ("coder_b_vs_consensus", "Coder B vs consensus"),
        ):
            metrics = (consensus.get(key) or {}).get("overall", {})
            lines.append(
                f"  {label}: agree={_format_percent(metrics.get('percent_agreement'))} "
                f"kappa={_format_number(metrics.get('cohen_kappa'))} "
                f"alpha_ord={_format_number(metrics.get('krippendorff_alpha_ordinal'))}"
            )

    disagreements = [
        (dimension["dimension_id"], item)
        for dimension in report.get("dimensions", [])
        for item in dimension.get("disagreements", [])
    ]
    if disagreements:
        lines.append("")
        lines.append(f"Disagreements ({len(disagreements)}):")
        for dimension_id, item in disagreements[:50]:
            suffix = ""
            if item.get("provider"):
                suffix = f"  [{item.get('provider')} / {item.get('target_id')}]"
            lines.append(
                f"  {item['unit_id']}  {dimension_id}  "
                f"a={item['coder_a']} b={item['coder_b']}{suffix}"
            )
        if len(disagreements) > 50:
            lines.append(f"  ... {len(disagreements) - 50} more in the JSON report")
    return "\n".join(lines) + "\n"
