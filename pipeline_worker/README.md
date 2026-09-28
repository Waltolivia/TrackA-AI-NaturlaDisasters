# Pipeline Worker

`pipeline_worker` is the durable middle layer between Disaster Monitor and the
AI probe runner. It consumes JSON messages without importing collector
internals, records each job in SQLite, invokes the AI runner in a subprocess,
and acknowledges or retries the queue message.

The repository root [README](../README.md) contains the recommended end-to-end
setup. This file documents the worker itself.

Install for mock testing with `uv sync --project pipeline_worker --extra dev`.
Before real API calls, add `--extra providers`.

## Queue behavior

The default `v5` layout is:

```text
disaster_monitor-v5/outbox/
  pending/       collector-created messages waiting for the worker
  processing/    messages claimed by the worker
  completed/     successful, deliberately skipped, or duplicate messages
  failed/        malformed messages or jobs that exhausted retries
```

The worker scans on startup and every polling interval. It does not depend on a
filesystem notification, so a restart cannot make it forget a pending file.
Claims and acknowledgements are same-filesystem moves.

Legacy v2 flat outboxes remain available with `--queue-layout flat`. Flat files
are not moved; the SQLite ledger prevents them from being executed repeatedly.

## Job states

| State | Meaning |
| --- | --- |
| `PENDING` | Valid probe trigger waiting to run |
| `RUNNING` | Claimed with a time-limited lease |
| `RETRY` | Failed temporarily and waiting for exponential backoff |
| `SUCCEEDED` | AI manifest reports every expected probe succeeded |
| `SKIPPED` | Lifecycle message or unsupported research hazard |
| `INVALID` | File is not valid trigger JSON |
| `DEAD` | Retry budget was exhausted; manual review is required |

The default worker accepts v5 `NEW_EVENT`, `STATUS_CHANGED`, and
`SEVERITY_CHANGED` messages. It acknowledges `EVENT_ENDED` without calling an
AI provider. Coordinate-only locations are skipped until reviewed enrichment is
available. The AI adapter also accepts v2 `NEW_EVENT` and `ESCALATION`.

## Commands

Run commands from the repository root:

```bash
uv run --project pipeline_worker pipeline-worker once
uv run --project pipeline_worker pipeline-worker run
uv run --project pipeline_worker pipeline-worker status
uv run --project pipeline_worker pipeline-worker retry MSG-example
```

`once` discovers the current queue and processes every ready job before
returning. Limit a manual pilot to one job with:

```bash
uv run --project pipeline_worker pipeline-worker once --max-jobs 1
```

Global options go before the command:

```bash
uv run --project pipeline_worker pipeline-worker \
  --targets ai_probe_runner/config/targets.local.json \
  --max-attempts 3 \
  --poll-seconds 5 \
  run
```

## Important configuration

| Option | Default | Purpose |
| --- | --- | --- |
| `--outbox` | `disaster_monitor-v5/outbox` | Collector queue root |
| `--state-db` | `pipeline_data/worker.db` | Durable worker ledger |
| `--targets` | mock targets | AI experimental conditions |
| `--question-bank-dir` | AI question banks | Versioned prompt templates |
| `--output` | `pipeline_data/results` | AI cycle archive |
| `--queue-layout` | `v5` | Use `flat` only for v2 |
| `--max-attempts` | `3` | Attempts before `DEAD` |
| `--retry-base-seconds` | `30` | Exponential retry base |
| `--lease-seconds` | `7200` | Crash-recovery claim lease |
| `--job-timeout-seconds` | `7200` | Maximum AI subprocess time |
| `--probe-delay-seconds` | `0` | Delay between provider calls |

Paths are resolved against the repository root, not the terminal's current
directory. The AI subprocess runs from `ai_probe_runner/`, allowing that
module's local `.env` file to load normally.

## Reliability model

- `message_id` is the worker job ID for v5. A SHA-256-derived ID is used for v2.
- A unique trigger hash rejects conflicting reuse of a message ID.
- The SQLite lease lets a future worker recover a job after a process crash.
- The AI cycle uses the same job ID and `--resume` on every attempt.
- Successful question/target pairs are skipped during a resumed cycle.
- Changed triggers, question banks, or target configurations cannot be resumed
  into an older cycle.
- Original error records remain in `probes.jsonl` for research auditing.

Do not run two workers against the same outbox with separate worker databases.
For the initial deployment, use one worker process and one persistent database.
