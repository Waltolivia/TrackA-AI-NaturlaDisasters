from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .reliability import compute_reliability, render_text_report
from .rubric import Rubric, default_rubric_path, load_rubric
from .worksheets import (
    BLIND_MAP_FILENAME,
    DEFAULT_CODERS,
    UNITS_FILENAME,
    coder_sheet_path,
    collect_units,
    discover_responses_files,
    load_units,
    read_sheet,
    write_workspace,
)

log = logging.getLogger("intercoder_reliability")
REPORT_FILENAME = "reliability-report.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="intercoder-reliability",
        description=(
            "Export provider-blind coding worksheets from Track A AI responses "
            "and compute intercoder agreement."
        ),
    )
    result.add_argument(
        "--rubric",
        type=Path,
        default=default_rubric_path(),
        help="Coding rubric JSON (default: the shipped study-v3 rubric)",
    )
    result.add_argument("--verbose", action="store_true")
    subparsers = result.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser(
        "export", help="Build blind coding worksheets from responses.json files"
    )
    export.add_argument(
        "--results-root",
        type=Path,
        help="Directory searched recursively for responses.json files",
    )
    export.add_argument(
        "--responses",
        type=Path,
        action="append",
        default=[],
        help="Explicit responses.json file (repeatable)",
    )
    export.add_argument("--output", type=Path, default=Path("coding"))
    export.add_argument(
        "--coders",
        default=",".join(DEFAULT_CODERS),
        help="Comma-separated coder labels, at least two",
    )
    export.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing workspace instead of refusing",
    )

    validate = subparsers.add_parser(
        "validate", help="Check coder sheets for missing, duplicate, or out-of-range scores"
    )
    validate.add_argument("--workspace", type=Path, default=Path("coding"))
    validate.add_argument(
        "--coder",
        action="append",
        default=[],
        help="Coder label to validate (repeatable; default: every coder-*.csv found)",
    )
    validate.add_argument("--units", type=Path, help="units.jsonl path")

    reliability = subparsers.add_parser(
        "reliability",
        help="Compute percent agreement, Cohen's kappa, and Krippendorff's alpha",
    )
    reliability.add_argument("--workspace", type=Path, default=Path("coding"))
    reliability.add_argument("--coder-a", type=Path)
    reliability.add_argument("--coder-b", type=Path)
    reliability.add_argument("--units", type=Path)
    reliability.add_argument("--blind-map", type=Path)
    reliability.add_argument(
        "--consensus",
        type=Path,
        help="Optional adjudicated sheet that records how disagreements were resolved",
    )
    reliability.add_argument(
        "--output", type=Path, help=f"JSON report path (default: workspace/{REPORT_FILENAME})"
    )
    reliability.add_argument(
        "--no-disagreements", action="store_true", help="Omit the disagreement list"
    )
    reliability.add_argument(
        "--reveal",
        action="store_true",
        help="Attach provider/model from blind_map.json to each disagreement",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    rubric = load_rubric(args.rubric)
    if args.command == "export":
        return _export(args, rubric)
    if args.command == "validate":
        return _validate(args, rubric)
    if args.command == "reliability":
        return _reliability(args, rubric)
    raise SystemExit(f"Unknown command: {args.command}")


def _export(args: argparse.Namespace, rubric: Rubric) -> int:
    paths = list(args.responses or [])
    if args.results_root:
        paths.extend(discover_responses_files(args.results_root))
    if not paths:
        raise SystemExit("export requires --results-root or --responses")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit("responses file not found: " + ", ".join(missing))
    coders = tuple(
        coder.strip() for coder in str(args.coders).split(",") if coder.strip()
    )
    if len(coders) < 2:
        raise SystemExit(
            "at least two coder labels are required for intercoder reliability"
        )
    units, blind_map, stats = collect_units(paths)
    if not units:
        raise SystemExit(
            "no codable responses were found (all probes were empty or failed)"
        )
    result = write_workspace(
        units=units,
        blind_map=blind_map,
        output_dir=args.output,
        rubric=rubric,
        coders=coders,
        overwrite=args.overwrite,
    )
    result["stats"] = stats
    print(json.dumps(result, indent=2))
    log.info("exported %s coding units to %s", len(units), args.output)
    log.info(
        "keep %s private: it maps blind units back to providers",
        Path(args.output) / BLIND_MAP_FILENAME,
    )
    return 0


def _validate(args: argparse.Namespace, rubric: Rubric) -> int:
    workspace = args.workspace
    units_path = args.units or workspace / UNITS_FILENAME
    unit_ids = (
        [unit["unit_id"] for unit in load_units(units_path)]
        if units_path.is_file()
        else []
    )
    coders = tuple(args.coder) or _discover_coders(workspace)
    if not coders:
        raise SystemExit(f"no coder sheets found in {workspace}")
    report: dict[str, object] = {
        "workspace": str(workspace),
        "unit_count": len(unit_ids),
        "coders": {},
    }
    problem_count = 0
    for coder in coders:
        path = coder_sheet_path(workspace, coder)
        if not path.is_file():
            report["coders"][coder] = {
                "sheet": str(path),
                "problems": ["sheet not found"],
            }
            problem_count += 1
            continue
        scores, problems = read_sheet(path, rubric)
        unknown = sorted(set(scores) - set(unit_ids)) if unit_ids else []
        missing = sorted(set(unit_ids) - set(scores)) if unit_ids else []
        incomplete = sorted(
            unit_id
            for unit_id, entry in scores.items()
            if any(entry.get(dimension) is None for dimension in rubric.dimension_ids)
        )
        report["coders"][coder] = {
            "sheet": str(path),
            "coded_units": len(scores),
            "missing_units": missing,
            "unknown_units": unknown,
            "incomplete_units": incomplete,
            "problems": problems,
        }
        problem_count += len(problems) + len(missing) + len(unknown) + len(incomplete)
    report["problem_count"] = problem_count
    report["ok"] = problem_count == 0
    print(json.dumps(report, indent=2))
    if problem_count:
        log.warning("validation found %s problem(s)", problem_count)
        return 1
    log.info("sheets are complete and in range")
    return 0


def _reliability(args: argparse.Namespace, rubric: Rubric) -> int:
    workspace = args.workspace
    coder_a_path = args.coder_a or coder_sheet_path(workspace, "a")
    coder_b_path = args.coder_b or coder_sheet_path(workspace, "b")
    for path in (coder_a_path, coder_b_path):
        if not path.is_file():
            raise SystemExit(f"coder sheet not found: {path}")
    units_path = args.units or workspace / UNITS_FILENAME
    scores_a, problems_a = read_sheet(coder_a_path, rubric)
    scores_b, problems_b = read_sheet(coder_b_path, rubric)

    blind_map: dict[str, dict[str, object]] = {}
    if args.reveal:
        blind_path = args.blind_map or workspace / BLIND_MAP_FILENAME
        if blind_path.is_file():
            payload = json.loads(blind_path.read_text(encoding="utf-8"))
            blind_map = payload.get("units", {}) if isinstance(payload, dict) else {}
        else:
            log.warning("--reveal requested but %s was not found", blind_path)

    report = compute_reliability(
        rubric=rubric,
        coder_a=scores_a,
        coder_b=scores_b,
        blind_map=blind_map,
        include_disagreements=not args.no_disagreements,
    )
    report["coder_a"] = {"label": coder_a_path.stem, "sheet": str(coder_a_path)}
    report["coder_b"] = {"label": coder_b_path.stem, "sheet": str(coder_b_path)}
    report["units"] = {
        "units_file": str(units_path) if units_path.is_file() else None,
        "unit_count": len(load_units(units_path)) if units_path.is_file() else 0,
    }
    report["sheet_problems"] = {"coder_a": problems_a, "coder_b": problems_b}
    if args.consensus:
        consensus_scores, consensus_problems = read_sheet(args.consensus, rubric)
        report["consensus"] = {
            "sheet": str(args.consensus),
            "problems": consensus_problems,
            "coder_a_vs_consensus": compute_reliability(
                rubric=rubric,
                coder_a=scores_a,
                coder_b=consensus_scores,
                include_disagreements=False,
            ),
            "coder_b_vs_consensus": compute_reliability(
                rubric=rubric,
                coder_a=scores_b,
                coder_b=consensus_scores,
                include_disagreements=False,
            ),
        }

    output = args.output or workspace / REPORT_FILENAME
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(render_text_report(report))
    log.info("wrote %s", output)
    return 0


def _discover_coders(workspace: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.name[len("coder-") : -len(".csv")]
            for path in Path(workspace).glob("coder-*.csv")
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
