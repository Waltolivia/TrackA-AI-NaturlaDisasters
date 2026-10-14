# Track A: AI Natural-Disaster Data Pipeline

This repository collects official alerts and supplemental public
natural-disaster event metadata, then automatically probes configured AI models
with a reproducible bank of disaster questions.
The current integration uses Disaster Monitor v5, a durable pipeline worker,
and the AI probe runner.

## Repository map

| Module | What it owns |
| --- | --- |
| `disaster_monitor-v5/` | Current ground-truth collector, event matching, lifecycle, archives, and JSON queue |
| `pipeline_worker/` | Queue claiming, deduplication, retries, crash recovery, and AI-runner invocation |
| `ai_probe_runner/` | Question selection, provider API calls, resumable probe cycles, and response archives |
| `deployment/` | Linux `systemd` templates and unattended-operation instructions |
| `legacy_collectors/` | Inactive earlier collectors retained for history and compatibility testing |

Only the first three modules participate in the current pipeline. Do not start
a collector under `legacy_collectors/` for normal operation.

### Recommended storage settings

| Service | Role in this project | Recommended now |
| --- | --- | --- |
| Local SQLite/files | Live working copy and retry state | Always on |
| Amazon S3 | Primary shared, human-readable ground-truth and AI archive | **On** for the study |
| Amazon DynamoDB | Optional older ground-truth retention/cleanup tier | **Off** unless the team deliberately wants local deletion |

S3 and DynamoDB do not compete for the same job. S3 stores the readable files
for both halves of the study, immediately, beneath one `EVT-...` folder.
DynamoDB contains only older ground-truth database records and never contains
AI probe output. You do not need a DynamoDB table to run the pipeline.

The modules communicate through versioned JSON. The worker does not import the
ground-truth collector's database or matching code.

```text
Disaster Monitor v5
        |
        | JSON message
        v
outbox/pending -> Pipeline Worker -> AI Probe Runner -> pipeline_data/results
        |                                      |
        +---------- same EVT folder -----------+
                           |
                           v
                 private shared S3 archive
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
   failed probes. After eight attempts it moves to `outbox/failed/`.
8. When S3 is enabled, ground truth and completed AI files upload beneath the
   same `EVT-...` prefix. Upload retries never repeat completed AI probes.

The worker probes these v5 actions:

- `NEW_EVENT`
- `STATUS_CHANGED`
- `SEVERITY_CHANGED`

`EVENT_ENDED` is recorded and acknowledged without spending API credits.
Unsupported hazards are also recorded as `SKIPPED`, not retried forever.

## Already set up? Start the live pipeline

Use exactly two terminals. Both commands assume each terminal starts at the
repository root.

**Terminal 1 — ground truth:**

```bash
source deployment/local.env
cd disaster_monitor-v5
.venv/bin/python -m disaster_monitor.main
```

**Terminal 2 — AI worker:**

```bash
source deployment/local.env
uv run --project pipeline_worker pipeline-worker \
  --targets ai_probe_runner/config/targets.study-v2.json \
  --poll-seconds 5 \
  run
```

Leave both running. Stop each with **Control+C**. View local readable output in
`pipeline_data/results/.../EVT-.../EVT-..._AI/AI_RESULTS.md`, or browse the
same event in the shared S3 bucket. If this is a new computer, complete the
numbered setup below first.

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

If Terminal shows a warning that `VIRTUAL_ENV` points at another project,
run `deactivate` once. The command still uses the correct uv environment, but
deactivating removes the confusing warning.

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
- Results appear under
  `pipeline_data/results/YYYY/Month/Week/EVT-.../EVT-..._AI/runs/MSG-.../`.
- Open the `AI_RESULTS.md` directly inside `EVT-..._AI/` first; use the
  adjacent `responses.json` for compact analysis data. Exact historical cycles
  remain under `runs/`.
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
The worker starts the AI runner for you; you do not need a third terminal.

The current cost-controlled study target file is committed without secrets:

```bash
python -m json.tool \
  ai_probe_runner/config/targets.study-v2.json >/dev/null
```

It enables all three approved providers. A successful event runs nine questions
against three models, for 27 probes. Use an ignored, isolated test queue so a
previous mock run cannot suppress the fixture as a duplicate:

```bash
mkdir -p local_test/outbox/{pending,processing,completed,failed}
cp pipeline_worker/examples/v5.flash-flood.json \
  local_test/outbox/pending/provider-test.json
```

Run one controlled job:

```bash
uv run --project pipeline_worker pipeline-worker \
  --outbox local_test/outbox \
  --state-db local_test/worker.db \
  --output local_test/results \
  --targets ai_probe_runner/config/targets.study-v2.json \
  once --max-jobs 1
```

Expect `expected_probe_count` and `completed_probe_count` to both be 27, with
`failed_probe_count` equal to zero. Inspect the manifest and `probes.jsonl` for
all three providers. The worker reports success only when every expected probe
completed. To troubleshoot one account, temporarily disable the other targets
in an ignored `targets.local.json`; do not change the committed study file.

Google currently offers a free tier for the selected Flash-Lite model, so the
initial test does not require Google billing. Free-tier data handling and quota
differ from paid usage; confirm the team's research-data policy before launch.

## 5. Configure the shared S3 archive

S3 is optional for local development but is the primary shared archive for the
study. Only one teammate should create the shared private bucket. Everyone
running the pipeline receives the same bucket name, region, and prefix plus an
authorized AWS identity.

After the bucket owner completes
[`deployment/S3_SETUP.md`](deployment/S3_SETUP.md), create your ignored local
settings file from the repository root:

```bash
cp deployment/local.env.example deployment/local.env
```

Edit only the placeholder email and shared bucket name, then load it in every
new terminal that runs a pipeline process:

```bash
source deployment/local.env
```

Terminal windows do not share exported settings. If the collector and worker
use two terminals, run the appropriate `source` command in both. Keep
`DYNAMODB_ARCHIVE_ENABLED=false` for the initial study deployment.

Do not put AWS keys in this file or in `ai_probe_runner/.env`. Configure a
dedicated AWS identity once with `aws configure`; on an EC2 VM, use an instance
role. Verify the current identity and bucket before starting:

```bash
aws sts get-caller-identity
aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/"
```

The shared structure is:

```text
s3://BUCKET/disaster_monitor-v5/archive/YYYY/Month/Week/EVT-.../
  EVT-..._weather/     ground-truth report and JSON
  EVT-..._AI/          latest readable results and all MSG-specific runs
```

## 6. Run the live ground-truth collector

Set up v5 in its own environment:

```bash
cd disaster_monitor-v5
uv venv --python 3.11
uv pip install -r requirements.txt
```

Load the shared settings. Because this terminal is now inside
`disaster_monitor-v5/`, the file is one directory up:

```bash
source ../deployment/local.env
```

Start the collector:

```bash
.venv/bin/python -m disaster_monitor.main
```

Leave this terminal open during the first test. The collector suppresses its
first successful source sync so that startup does not generate hundreds of
historical jobs. New meaningful changes after that sync enter
`outbox/pending/`.

## 7. Run the worker continuously

Open a second terminal at the repository root:

```bash
source deployment/local.env
uv run --project pipeline_worker pipeline-worker \
  --targets ai_probe_runner/config/targets.study-v2.json \
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
- Stable archive coordinates (`year`, `month`, `week`, and event prefix)

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
- `AI_RESULTS.md`, the recommended human-readable view
- `responses.json`, the compact analysis-friendly view

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
7. Enable and verify the shared S3 archive; confirm both `weather` and `AI`
   folders appear beneath one event before relying on unattended collection.
8. Monitor `DEAD` jobs and queue growth daily during the initial study.

The v5 collector already includes health output, rotating logs, database
backups, and a macOS launchd template. Start both services manually first; only
enable automatic startup after the real-provider pilot succeeds.

### AWS storage roles

S3 is the primary shared file archive and updates within seconds of local
writes. It preserves readable ground-truth and AI files beneath the same event
prefix. See [`deployment/S3_SETUP.md`](deployment/S3_SETUP.md).

The following older DynamoDB feature remains optional and separate:

When explicitly enabled, the collector keeps a rolling local window of one
week (`LOCAL_RETENTION_DAYS`).
Finished events older than that window are copied to an AWS DynamoDB table and
only then deleted from SQLite and `archive/`, so the local disk never grows
without bound. It is off by default; turn it on deliberately with
`DYNAMODB_ARCHIVE_ENABLED=true` plus `AWS_REGION`/`AWS_DYNAMODB_TABLE` and
normal boto3 credentials. The legacy name `AWS_ARCHIVE_ENABLED` is still
accepted for existing deployments. See
[`disaster_monitor-v5/README.md`](disaster_monitor-v5/README.md#optional-secondary-tier-one-local-week-then-dynamodb)
for details and the `python -m disaster_monitor.archive_cli` commands.

## Common setup problems

| What you see | What it usually means | Fix |
| --- | --- | --- |
| `S3_BUCKET is required` | Settings were not loaded in this terminal | Run `source deployment/local.env` from the repository root |
| `NoCredentialsError` | boto3 cannot find an AWS identity | Run `aws configure`, then `aws sts get-caller-identity` |
| `AccessDenied` | The identity lacks access or the bucket/prefix differs | Compare the three S3 values with the team lead and check the IAM policy |
| Worker shows no jobs | Initial collector sync is intentionally suppressed, or no alert changed | Use the synthetic mock procedure in section 3 to verify the connection |
| Missing provider key | `.env` is absent or in the wrong folder | Confirm the exact path is `ai_probe_runner/.env` |
| `VIRTUAL_ENV ... does not match` | A different virtual environment is active | Run `deactivate`, then rerun the uv command |
| AI output exists locally but not in S3 | The upload is pending/retrying | Check worker logs and look for `.s3-uploaded.json` in the exact run folder |

## Important current boundaries

- EONET sometimes provides coordinates instead of a human-readable place. The
  worker records coordinate-only jobs as `SKIPPED` until location enrichment is
  reviewed, preventing unrealistic location prompts.
- NWS is the authoritative alert trigger. EONET is supplemental discovery
  metadata and is not treated as authoritative spatial or temporal ground truth.
- The pipeline currently probes flood, wildfire, tropical cyclone, tornado,
  and earthquake events.
- Provider SDK errors are retained in research output. Temporary job failures
  retry with exponential backoff, up to eight attempts by default.
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
- [ ] One S3 test event contains adjacent `EVT-..._weather` and `EVT-..._AI` folders.
- [ ] `AI_RESULTS.md` is readable in the AI folder and the exact `MSG-...` run is retained.
- [ ] The team approves `STUDY_PROTOCOL.md` and the frozen study target file.
- [ ] The clean merged commit is tagged `study-v2.0.0` and that tag is deployed.
- [ ] The team records the Git commit, target configuration, and collection start time.

For details specific to the worker or provider configuration, see
[`pipeline_worker/README.md`](pipeline_worker/README.md) and
[`ai_probe_runner/README.md`](ai_probe_runner/README.md). The frozen research
decisions are in [`STUDY_PROTOCOL_V2.md`](STUDY_PROTOCOL_V2.md), and unattended Linux
setup is in [`deployment/README.md`](deployment/README.md).
