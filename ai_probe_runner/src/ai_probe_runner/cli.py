from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .questions import load_trigger
from .runner import run_cycle


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run reproducible AI probes for a natural-disaster event"
    )
    input_group = result.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--trigger", type=Path, help="Ground-truth trigger JSON")
    input_group.add_argument(
        "--hazard-family",
        help="Manual test category, such as flood, wildfire, or earthquake",
    )
    result.add_argument("--event", help="Official event name for manual input")
    result.add_argument("--area", help="General affected area for manual input")
    result.add_argument("--source", default="manual")
    result.add_argument("--source-id")
    result.add_argument("--cycle-id")
    result.add_argument(
        "--targets", type=Path, default=Path("config/targets.mock.json")
    )
    result.add_argument(
        "--question-bank-dir",
        type=Path,
        default=Path("config/question_banks"),
    )
    result.add_argument("--output", type=Path, default=Path("data"))
    result.add_argument("--delay-seconds", type=float, default=0.0)
    result.add_argument(
        "--fail-on-probe-error",
        action="store_true",
        help="Exit with status 1 when any provider probe fails (recommended for automation)",
    )
    return result


def main() -> None:
    load_dotenv()
    args = parser().parse_args()
    if args.trigger:
        trigger = load_trigger(args.trigger)
    else:
        if not args.event or not args.area:
            raise SystemExit(
                "--event and --area are required with --hazard-family"
            )
        trigger = _manual_trigger(args)

    result = run_cycle(
        trigger=trigger,
        targets_path=args.targets,
        bank_dir=args.question_bank_dir,
        output_dir=args.output,
        cycle_id=args.cycle_id,
        delay_seconds=args.delay_seconds,
    )
    print(json.dumps(result, indent=2))
    if args.fail_on_probe_error and result["failed_probe_count"]:
        raise SystemExit(1)


def _manual_trigger(args: argparse.Namespace) -> dict[str, Any]:
    source_id = args.source_id or f"manual-{uuid.uuid4()}"
    trigger: dict[str, Any] = {
        "source": args.source,
        "source_id": source_id,
        "hazard_family": args.hazard_family,
        "event": args.event,
        "area": args.area,
    }
    if args.cycle_id:
        trigger["cycle_id"] = args.cycle_id
    return trigger


if __name__ == "__main__":
    main()
