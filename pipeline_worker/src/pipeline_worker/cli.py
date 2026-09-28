from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import WorkerConfig, default_config
from .worker import PipelineWorker


def parser() -> argparse.ArgumentParser:
    defaults = default_config()
    result = argparse.ArgumentParser(
        description="Run the Track A ground-truth to AI-probe pipeline"
    )
    result.add_argument("--outbox", type=Path, default=defaults.outbox)
    result.add_argument("--state-db", type=Path, default=defaults.state_db)
    result.add_argument("--targets", type=Path, default=defaults.targets)
    result.add_argument(
        "--question-bank-dir", type=Path, default=defaults.question_bank_dir
    )
    result.add_argument("--output", type=Path, default=defaults.output_dir)
    result.add_argument("--ai-project", type=Path, default=defaults.ai_project)
    result.add_argument("--queue-layout", choices=("v5", "flat"), default="v5")
    result.add_argument("--poll-seconds", type=float, default=5.0)
    result.add_argument("--max-attempts", type=int, default=3)
    result.add_argument("--retry-base-seconds", type=float, default=30.0)
    result.add_argument("--lease-seconds", type=int, default=7200)
    result.add_argument("--job-timeout-seconds", type=int, default=7200)
    result.add_argument("--probe-delay-seconds", type=float, default=0.0)
    subcommands = result.add_subparsers(dest="command", required=True)
    once = subcommands.add_parser("once", help="Scan and process ready jobs, then exit")
    once.add_argument("--max-jobs", type=int)
    subcommands.add_parser("run", help="Continuously scan and process jobs")
    status = subcommands.add_parser("status", help="Show queue and recent job status")
    status.add_argument("--limit", type=int, default=20)
    retry = subcommands.add_parser("retry", help="Manually requeue a final job")
    retry.add_argument("job_id")
    return result


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = WorkerConfig(
        outbox=args.outbox,
        state_db=args.state_db,
        targets=args.targets,
        question_bank_dir=args.question_bank_dir,
        output_dir=args.output,
        ai_project=args.ai_project,
        queue_layout=args.queue_layout,
        poll_seconds=args.poll_seconds,
        max_attempts=args.max_attempts,
        retry_base_seconds=args.retry_base_seconds,
        lease_seconds=args.lease_seconds,
        job_timeout_seconds=args.job_timeout_seconds,
        probe_delay_seconds=args.probe_delay_seconds,
    )
    worker = PipelineWorker(config)

    if args.command == "once":
        print(json.dumps(worker.run_once(max_jobs=args.max_jobs), indent=2))
    elif args.command == "run":
        worker.run_forever()
    elif args.command == "status":
        print(json.dumps(worker.database.summary(limit=args.limit), indent=2))
    elif args.command == "retry":
        if not worker.database.retry(args.job_id):
            raise SystemExit(f"Job is not retryable or does not exist: {args.job_id}")
        print(json.dumps({"job_id": args.job_id, "status": "PENDING"}, indent=2))


if __name__ == "__main__":
    main()
