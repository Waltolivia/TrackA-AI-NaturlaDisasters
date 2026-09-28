# Track A: AI Natural-Disaster Data Pipeline

This repository collects official natural-disaster events and automatically
probes configured AI models with a reproducible bank of disaster questions.
The current integration uses Disaster Monitor v5, a durable pipeline worker,
and the AI probe runner.

## Repository map

| Module | What it owns |
| --- | --- |
| `disaster_monitor-v5/` | Current ground-truth collector, event matching, lifecycle, archives, and JSON queue |
| `pipeline_worker/` | Queue claiming, deduplication, retries, crash recovery, and AI-runner invocation |
| `ai_probe_runner/` | Question selection, provider API calls, resumable probe cycles, and response archives |
| `legacy_collectors/` | Inactive earlier collectors retained for history and compatibility testing |

Only the first three modules participate in the current pipeline. Do not start
a collector under `legacy_collectors/` for normal operation.

The modules communicate through versioned JSON. The worker does not import the
ground-truth collector's database or matching code.

```text
Disaster Monitor v5
        |
        | JSON message
        v
outbox/pending -> Pipeline Worker -> AI Probe Runner -> pipeline_data/results
                       |
                       v
              pipeline_data/worker.db
```

## What happens for one event

1. Disaster Monitor polls NWS or NASA EONET.
2. It filters, deduplicates, and groups records into an event.
3. A meaningful live change is atomically written to `outbox/pending/`.
4. The worker records the unique `message_id` in SQLite and moves the file to
   `outbox/processing/`.
5. The AI runner combines five general questions with four matching hazard
   questions and calls every enabled target.
6. A completely successful job moves to `outbox/completed/`.
7. A failed job waits for exponential backoff and resumes only missing or
   failed probes. After three attempts it moves to `outbox/failed/`.

The worker probes these v5 actions:

- `NEW_EVENT`
- `STATUS_CHANGED`
- `SEVERITY_CHANGED`

`EVENT_ENDED` is recorded and acknowledged without spending API credits.
Unsupported hazards are also recorded as `SKIPPED`, not retried forever.

## 1. Install uv

This project uses [uv](https://docs.astral.sh/uv/) for Python environments and
locked dependencies.

Check whether it is installed:

```bash
uv --version
```

On macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen the terminal after installing uv.

## 2. Clone and install the pipeline

```bash
git clone https://github.com/Waltolivia/TrackA-AI-NaturlaDisasters.git
cd TrackA-AI-NaturlaDisasters
uv sync --project pipeline_worker --extra dev
```

That command installs the worker, local AI runner, and test tools into
`pipeline_worker/.venv`. It is enough for the free mock pipeline test.

## 3. Run the complete no-cost test

First run all automated tests:

```bash
uv run --project ai_probe_runner --extra dev pytest -q ai_probe_runner/tests
uv run --project pipeline_worker --extra dev pytest -q pipeline_worker/tests
PYTHONPATH=disaster_monitor-v5 \
  uv run --no-project \
  --with-requirements disaster_monitor-v5/requirements.txt \
  pytest -q disaster_monitor-v5/tests
```

Then place the synthetic v5 trigger into the real queue layout:

```bash
mkdir -p disaster_monitor-v5/outbox/pending
cp pipeline_worker/examples/v5.flash-flood.json \
  disaster_monitor-v5/outbox/pending/
```

Run the worker once. Its default target is the free local mock:

```bash
uv run --project pipeline_worker pipeline-worker once
```

Expected result:

- One job reports `SUCCEEDED`.
- Nine mock probes complete.
- The trigger moves from `outbox/pending/` to `outbox/completed/`.
- Results appear under `pipeline_data/results/YYYY-MM-DD/`.
- Worker state appears in `pipeline_data/worker.db`.

Inspect status at any time:

```bash
uv run --project pipeline_worker pipeline-worker status
```

The synthetic `message_id` is intentionally stable. Copying the same example
again tests deduplication; it will be acknowledged without another AI cycle.

## 4. Configure real AI providers

Install the three provider SDKs:

```bash
uv sync --project pipeline_worker --extra dev --extra providers
```

The provider dependency set includes an Intel-macOS-compatible cryptography
constraint to avoid requiring a newer local Rust compiler.

Create the ignored local key file:

```bash
cp ai_probe_runner/.env.example ai_probe_runner/.env
```

Edit `ai_probe_runner/.env`:

```dotenv
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

Never put keys in JSON, source code, Git, screenshots, or collected results.

Create the ignored real target file:

```bash
cp ai_probe_runner/config/targets.example.json \
  ai_probe_runner/config/targets.local.json
```

The example enables all three approved providers. A successful event therefore
runs nine questions against three models, for 27 probes. Run one controlled job:

```bash
uv run --project pipeline_worker pipeline-worker \
  --targets ai_probe_runner/config/targets.local.json \
  once --max-jobs 1
```

Expect `expected_probe_count` and `completed_probe_count` to both be 27, with
`failed_probe_count` equal to zero. Inspect the manifest and `probes.jsonl` for
all three providers. The worker reports success only when every expected probe
completed. To troubleshoot one account, temporarily disable the other targets
in the ignored local file; do not change the committed baseline.

## 5. Run the live ground-truth collector

Set up v5 in its own environment:

```bash
cd disaster_monitor-v5
uv venv --python 3.11
uv pip install -r requirements.txt
```

Set a descriptive NWS user agent with a real project contact:

```bash
export NWS_USER_AGENT='BYU-TrackA-DisasterResearch/1.0 (contact@example.edu)'
```

Start the collector:

```bash
.venv/bin/python -m disaster_monitor.main
```

Leave this terminal open during the first test. The collector suppresses its
first successful source sync so that startup does not generate hundreds of
historical jobs. New meaningful changes after that sync enter
`outbox/pending/`.

## 6. Run the worker continuously

Open a second terminal at the repository root:

```bash
uv run --project pipeline_worker pipeline-worker \
  --targets ai_probe_runner/config/targets.local.json \
  --poll-seconds 5 \
  run
```

Stop either program cleanly with **Control+C**. During the first live session,
keep `pipeline-worker status` open in another terminal and verify the first few
events manually.

For a no-cost live collector test, omit `--targets`; the worker will continue
using `targets.mock.json`.

## Worker commands

### Process ready jobs and exit

```bash
uv run --project pipeline_worker pipeline-worker once
```

### Process only one ready job

```bash
uv run --project pipeline_worker pipeline-worker once --max-jobs 1
```

### Run continuously

```bash
uv run --project pipeline_worker pipeline-worker run
```

### Inspect the ledger

```bash
uv run --project pipeline_worker pipeline-worker status --limit 50
```

### Retry a reviewed final failure

```bash
uv run --project pipeline_worker pipeline-worker retry MSG-REPLACE-ME
```

Manual retry resets that job's attempt budget. Because AI cycles are resumable,
question/target pairs that already succeeded are not called again.

## Queue and job states

| Location/state | Meaning |
| --- | --- |
| `outbox/pending/` | Collector created it; worker has not claimed it |
| `outbox/processing/` | Worker owns it or will recover it after restart |
| `outbox/completed/` | Probe succeeded, message was skipped intentionally, or duplicate was acknowledged |
| `outbox/failed/` | Invalid trigger or retry budget exhausted |
| `PENDING` | Valid job waiting in the SQLite ledger |
| `RUNNING` | Job has an active time-limited lease |
| `RETRY` | Temporary failure waiting for backoff |
| `SUCCEEDED` | Every expected AI probe succeeded |
| `SKIPPED` | Non-probe action or unsupported hazard |
| `INVALID` | Malformed JSON |
| `DEAD` | Manual review required |

Do not manually move files out of `processing/` while the worker is running.
Use the worker status and retry commands so the filesystem and ledger remain in
agreement.

## Supported trigger formats

The preferred format is Disaster Monitor v5 schema 3. It includes:

- Unique `message_id`
- Stable `event_id`
- `action`
- `disaster.type`
- `disaster.location`
- Source timestamps and provenance

The AI adapter and worker also support v2 `NEW_EVENT` and `ESCALATION` objects.
To consume the older flat directory explicitly:

```bash
uv run --project pipeline_worker pipeline-worker \
  --queue-layout flat \
  --outbox legacy_collectors/disaster_monitor-v2/outbox \
  once
```

## Reproducibility and retry behavior

Every AI cycle archives:

- Exact raw and normalized trigger
- Rendered questions
- Target and question-bank hashes
- Git commit and runtime
- Provider-reported model and usage
- Every successful or failed attempt

The worker uses the v5 `message_id` as the cycle ID. If a cycle is interrupted,
the same ID locates the existing cycle even after the calendar date changes.
`--resume` verifies that the trigger, target file, question banks, and expected
probe count are unchanged. It then calls only failed or missing probe pairs.

Changing a target file or question bank during a retry is rejected. This avoids
mixing different research conditions inside one cycle.

## Preparing for 24/7 use

Before leaving the pipeline unattended:

1. Complete the mock test and a controlled all-provider pilot.
2. Confirm the chosen models are available and billing limits are set.
3. Put the repository and `pipeline_data/` on persistent storage.
4. Back up `pipeline_data/worker.db`, AI results, and the collector database.
5. Use one worker process. Do not run two workers with separate state databases.
6. Use `systemd`, launchd, Docker Compose, or another supervisor to restart the
   collector and worker after a reboot.
7. Upload completed result directories to S3 or another durable store before
   deleting any local data.
8. Monitor `DEAD` jobs and queue growth daily during the initial study.

The v5 collector already includes health output, rotating logs, database
backups, and a macOS launchd template. Start both services manually first; only
enable automatic startup after the real-provider pilot succeeds.

## Important current boundaries

- EONET sometimes provides coordinates instead of a human-readable place. The
  worker records coordinate-only jobs as `SKIPPED` until location enrichment is
  reviewed, preventing unrealistic location prompts.
- The pipeline currently probes flood, wildfire, tropical cyclone, tornado,
  and earthquake events.
- Provider SDK errors are retained in research output. Temporary job failures
  retry with exponential backoff, up to three attempts by default.
- v5 files are atomically written before they appear in `pending/`. A future
  hardening step could put outbox creation in the same SQLite transaction as
  event updates, but this is not required for the Wednesday integration run.

## Wednesday readiness checklist

- [ ] All three test commands pass.
- [ ] Synthetic v5 message completes nine mock probes.
- [ ] Duplicate synthetic message does not create another cycle.
- [ ] One real provider completes one event successfully.
- [ ] All approved providers complete one event successfully.
- [ ] Collector and worker run together for at least one supervised hour.
- [ ] `pipeline-worker status` has no unexplained `DEAD` jobs.
- [ ] Result and SQLite backup locations are confirmed.
- [ ] The team records the Git commit, target configuration, and collection start time.

For details specific to the worker or provider configuration, see
[`pipeline_worker/README.md`](pipeline_worker/README.md) and
[`ai_probe_runner/README.md`](ai_probe_runner/README.md).
