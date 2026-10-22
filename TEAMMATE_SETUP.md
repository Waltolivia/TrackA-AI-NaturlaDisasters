# New teammate setup

This is the shortest complete setup for a computer that will run the Track A
collector and AI worker. Complete the one-time setup once, run the free smoke
test, and then use the two normal start commands whenever the pipeline runs.

## Get these values from the bucket owner

The bucket owner should privately provide:

- A dedicated AWS access key ID for this person or machine
- Its matching AWS secret access key
- The shared S3 bucket name
- The AWS region, normally `us-west-2`
- The three AI provider keys
- A real email address for the NWS user-agent setting

The AWS access key is not an AI key. It is entered with `aws configure` and
must not be pasted into either repository `.env` file. Do not use an AWS root
account key or another teammate's key.

## 1. Install the required command-line tools

Install Git and Python 3.11 if they are not already available. Check for uv:

```bash
uv --version
```

If it is missing on macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen Terminal. Install the
[AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
if this does not work:

```bash
aws --version
```

## 2. Clone and install the project

```bash
git clone https://github.com/Waltolivia/TrackA-AI-NaturlaDisasters.git
cd TrackA-AI-NaturlaDisasters
uv sync --project pipeline_worker --extra dev --extra providers
```

Install the ground-truth collector in its own environment:

```bash
cd disaster_monitor-v5
uv venv --python 3.11
uv pip install -r requirements.txt
cd ..
```

If uv warns that another `VIRTUAL_ENV` is active, run `deactivate` and repeat
the command.

## 3. Add the AI provider keys

```bash
cp ai_probe_runner/.env.example ai_probe_runner/.env
```

Open `ai_probe_runner/.env` and fill in the supplied values:

```dotenv
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

Save the file. Its exact path must be `ai_probe_runner/.env`; do not rename it
to `env.txt`. It is ignored by Git.

## 4. Configure this machine's AWS identity

Run:

```bash
aws configure --profile tracka
```

Enter the dedicated values supplied for this machine:

```text
AWS Access Key ID: supplied access key ID
AWS Secret Access Key: supplied secret access key
Default region name: us-west-2
Default output format: json
```

The AWS CLI stores these credentials outside the repository. Verify them:

```bash
aws sts get-caller-identity --profile tracka
```

The returned ARN should identify the IAM user created for this person or
machine. Stop and ask the bucket owner if it identifies the wrong account.

## 5. Add the shared non-secret settings

From the repository root:

```bash
cp deployment/local.env.example deployment/local.env
```

Open `deployment/local.env` and replace:

- `YOUR_EMAIL` with the supplied contact email
- `REPLACE_WITH_SHARED_BUCKET_NAME` with the exact bucket name
- `us-west-2` only if the bucket owner selected a different region

Keep these study settings unchanged:

```bash
export AWS_PROFILE='tracka'
export S3_PREFIX='disaster_monitor-v5/archive'
export S3_ARCHIVE_ENABLED=true
export DYNAMODB_ARCHIVE_ENABLED=false
```

Load and verify the settings:

```bash
source deployment/local.env
printf '%s\n' "$AWS_PROFILE" "$S3_BUCKET" "$S3_PREFIX" "$AWS_REGION"
aws sts get-caller-identity
aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/"
```

An empty S3 listing is normal before the first upload. `AccessDenied`,
`NoSuchBucket`, or a blank setting must be fixed before continuing.

## 6. Run the free S3 smoke test

This test uses the local mock AI provider and does not spend provider credits:

```bash
mkdir -p local_test/s3-smoke/outbox/pending
mkdir -p local_test/s3-smoke/outbox/processing
mkdir -p local_test/s3-smoke/outbox/completed
mkdir -p local_test/s3-smoke/outbox/failed

cp pipeline_worker/examples/v5.flash-flood.json \
  local_test/s3-smoke/outbox/pending/s3-test.json

uv run --project pipeline_worker pipeline-worker \
  --outbox local_test/s3-smoke/outbox \
  --state-db local_test/s3-smoke/worker.db \
  --output local_test/s3-smoke/results \
  --question-bank-dir ai_probe_runner/config/question_banks_v3 \
  --s3 \
  --s3-bucket "$S3_BUCKET" \
  --aws-region "$AWS_REGION" \
  once --max-jobs 1
```

Success means the summary contains:

```json
"processed": 1,
"succeeded": 1,
"failed": 0
```

Confirm that files reached the shared bucket:

```bash
aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/" --recursive
```

Look for `EVT-00000001_AI/AI_RESULTS.md`. If the test trigger was already run
with this exact `local_test/s3-smoke` state database, use a new folder such as
`local_test/s3-smoke-02` rather than deleting study data.

## 7. Start the live pipeline

Use two Terminal windows. Start each one at the repository root.

Terminal 1 — ground-truth collector:

```bash
source deployment/local.env
cd disaster_monitor-v5
.venv/bin/python -m disaster_monitor.main
```

Terminal 2 — AI worker:

```bash
source deployment/local.env
uv run --project pipeline_worker pipeline-worker \
  --targets ai_probe_runner/config/targets.study-v3-search.json \
  --question-bank-dir ai_probe_runner/config/question_banks_v3 \
  --poll-seconds 5 \
  run
```

Leave both Terminal windows open. Stop each process with **Control+C**. The
collector suppresses AI jobs during its initial source sync; new meaningful
events and changes after that sync enter the worker queue.

### Updating an already-running computer from V2

Do not delete or replace the existing databases. Before pulling the V3 change:

1. Stop both processes with **Control+C**.
2. Check worker status. If any job is `RUNNING` or `RETRY`, restart the old V2
   worker and allow it to finish before switching.
3. Copy these items to a dated backup while both processes are stopped:
   `disaster_monitor-v5/data/disaster_monitor.db`,
   `disaster_monitor-v5/outbox/`, `pipeline_data/worker.db`, and
   `pipeline_data/results/`.
4. Run `git pull`, then rerun
   `uv sync --project pipeline_worker --extra dev --extra providers`.
5. Start the collector normally and use the V3 worker command above.

Keeping `disaster_monitor.db` preserves the next `EVT-...` number. Keeping
`worker.db` preserves deduplication and retry history. Existing S3 event and run
folders stay in place; new UUID message IDs create new `runs/MSG-.../` folders.
Never run a second fresh collector against the same shared S3 prefix.

## 8. Find the results

Local human-readable AI output:

```text
pipeline_data/results/YYYY/Month/Week/EVT-.../EVT-..._AI/AI_RESULTS.md
```

Shared cloud layout:

```text
s3://BUCKET/disaster_monitor-v5/archive/YYYY/Month/Week/EVT-.../
  EVT-..._weather/
  EVT-..._AI/
```

List all cloud results:

```bash
source deployment/local.env
aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/" --recursive
```

Check the worker ledger:

```bash
uv run --project pipeline_worker pipeline-worker status --limit 20
```

Start with `AI_RESULTS.md` for reading. Use `responses.json` for analysis and
the `runs/MSG-.../` directory for the complete reproducibility record.

## Common problems

| Problem | Fix |
| --- | --- |
| `NoCredentialsError` | Run `aws configure --profile tracka`, then source `deployment/local.env` |
| `AccessDenied` | Ask the bucket owner to verify this IAM user has the S3 archive policy |
| `S3_BUCKET is required` | Run `source deployment/local.env` in this Terminal |
| Missing provider key | Confirm the file is exactly `ai_probe_runner/.env` |
| Worker has no jobs | Initial source sync is intentionally suppressed; use the smoke test first |
| AI result exists locally but not in S3 | Check worker logs; the upload will retry without rerunning paid probes |

For bucket-owner IAM instructions, see
[`deployment/S3_SETUP.md`](deployment/S3_SETUP.md). For design and operational
details, see the root [`README.md`](README.md).
