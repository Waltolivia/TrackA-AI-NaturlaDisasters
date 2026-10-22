# Shared S3 research archive

S3 is the primary off-machine archive for this project. The collector and AI
worker use the same bucket and prefix, while local SQLite databases and files
remain the recoverable working copy.

## Who does what

- **One bucket owner** completes sections 1 and 2 once, then sends teammates
  the bucket name, region, prefix, and a safe way to obtain AWS access.
- **Each computer or VM operator** completes section 3 once and loads the
  shared settings whenever starting the collector or worker.
- Nobody creates folders by hand. The programs create the year, month, week,
  event, weather, AI, and run prefixes automatically.
- Nobody makes the bucket public or commits AWS credentials.

DynamoDB is not part of this setup and is not required. Its separate optional
retention role is explained at the bottom of this page.

## Result layout

```text
s3://BUCKET/disaster_monitor-v5/archive/
  2026/October/Oct_12-Oct_18/EVT-00000001/
    EVT-00000001_weather/
      EVENT_REPORT.txt
      event.json
      alerts.json
      archive_manifest.json
    EVT-00000001_AI/
      AI_RESULTS.md
      responses.json
      trigger.raw.json
      LATEST.json
      runs/
        MSG-unique-trigger-id/
          AI_RESULTS.md
          responses.json
          trigger.raw.json
          trigger.json
          questions.json
          manifest.json
          probes.jsonl
          raw/
```

`event_id` connects everything about one disaster. `message_id` identifies the
exact collector change that caused one AI cycle. The short files directly in
`EVT-..._AI/` show the latest completed cycle; immutable `runs/MSG-.../`
folders preserve every cycle.

## 1. Bucket owner: create the bucket

The easiest setup is in the AWS Console:

1. Open **S3 → Create bucket**.
2. Choose one globally unique name, such as
   `byu-tracka-disaster-study-ACCOUNT-NUMBER`.
3. Choose one region and use it everywhere. `us-west-2` is a reasonable Utah
   default.
4. Leave **Block all public access** enabled.
5. Enable **Bucket Versioning** so accidental overwrites can be recovered.
6. Leave default encryption enabled with **SSE-S3**.
7. Create the bucket. Do not enable public website hosting or public access.

The application also requests SSE-S3 encryption on each upload. The bucket
owner should send operators exactly these three non-secret values:

```text
S3_BUCKET=the-created-bucket-name
S3_PREFIX=disaster_monitor-v5/archive
AWS_REGION=us-west-2
```

## 2. Bucket owner: create uploader access

For local testing, create a dedicated IAM user or role with programmatic
access. Replace both occurrences of `YOUR_BUCKET` in this least-privilege
policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTrackAArchive",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "disaster_monitor-v5/archive",
            "disaster_monitor-v5/archive/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadWriteTrackAArchive",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/disaster_monitor-v5/archive/*"
    }
  ]
}
```

Console path for a basic IAM-user setup:

1. Open **IAM → Policies → Create policy → JSON** and paste the policy above.
2. Save it as `TrackAStudyS3Archive` and attach it to a dedicated user or role.
3. For a local computer, create an access key for the CLI use case and deliver
   it privately to that operator. Prefer one identity per person or machine so
   access can be revoked without disrupting everyone.
4. Never create or share access keys for the AWS root account.

Team members who only browse or download results should receive their own
read-only identity. Do not put an AWS secret key in Git,
`ai_probe_runner/.env`, `deployment/local.env`, or a group text.

On an EC2 VM, prefer an instance role with the policy above so no long-lived
AWS secret is stored on disk.

## 3. Each operator: configure one computer

Install the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
if `aws --version` does not work. Configure the dedicated identity once:

```bash
aws configure
aws sts get-caller-identity
```

`boto3`, used by both Python processes, automatically uses this AWS profile.

From the repository root, create the ignored local settings file:

```bash
cp deployment/local.env.example deployment/local.env
```

Edit `deployment/local.env`. Replace the bucket placeholder and contact email;
leave the prefix and region equal to the bucket owner's values. Then load it:

```bash
source deployment/local.env
```

Run that `source` command in **every new terminal** opened at the repository
root. From inside `disaster_monitor-v5/`, use
`source ../deployment/local.env` instead. Shell variables from one terminal do
not automatically appear in another.

Verify the configuration before starting:

```bash
aws sts get-caller-identity
printf '%s\n' "$S3_BUCKET" "$S3_PREFIX" "$AWS_REGION"
aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/"
```

An empty final listing is okay for a new bucket. `AccessDenied`,
`NoSuchBucket`, or a blank setting is not.

For `systemd`, put the shared values in both `/etc/tracka/collector.env` and
`/etc/tracka/providers.env`. Templates are under `deployment/systemd/`.

## 4. Verify S3 without spending AI credits

Run the automated fake-S3 tests first:

```bash
uv run --project pipeline_worker --extra dev pytest -q pipeline_worker/tests
PYTHONPATH=disaster_monitor-v5 \
  uv run --no-project \
  --with-requirements disaster_monitor-v5/requirements.txt \
  pytest -q disaster_monitor-v5/tests
```

Then use the mock AI target with the real bucket:

```bash
source deployment/local.env
mkdir -p local_test/outbox/{pending,processing,completed,failed}
cp pipeline_worker/examples/v5.flash-flood.json \
  local_test/outbox/pending/s3-test.json

uv run --project pipeline_worker pipeline-worker \
  --outbox local_test/outbox \
  --state-db local_test/worker.db \
  --output local_test/results \
  --question-bank-dir ai_probe_runner/config/question_banks_v3 \
  --s3 \
  --s3-bucket "$S3_BUCKET" \
  --aws-region "$AWS_REGION" \
  once --max-jobs 1
```

Confirm the AI files exist:

```bash
aws s3 ls \
  "s3://$S3_BUCKET/disaster_monitor-v5/archive/2026/September/Sep_28-Sep_30/EVT-00000001/" \
  --recursive
```

The live collector creates the adjacent `EVT-..._weather/` folder whenever it
writes or updates a ground-truth event. Its local `data/s3_pending/` markers
remain until all ground-truth objects upload successfully. After this mock
check, run the live collector and worker using sections 6 and 7 of the root
[`README.md`](../README.md).

## Failure behavior

- Local files are written before an S3 upload is attempted.
- Collector uploads are queued in `disaster_monitor-v5/data/s3_pending/` and
  retried without losing the event.
- At collector startup, current local events are queued for idempotent S3
  reconciliation, so S3 can be enabled after collection has already begun.
- A completed AI cycle gets `.s3-uploaded.json` only after all S3 objects are
  accepted.
- Missing AI upload markers are retried independently of AI probing. An S3
  outage does not repeat completed paid API requests.
- Uploading deterministic keys is idempotent. Repeating an interrupted upload
  safely replaces the same current snapshot.

## Optional DynamoDB compatibility

The teammate's DynamoDB retention archive remains available through
`DYNAMODB_ARCHIVE_ENABLED`; the old `AWS_ARCHIVE_ENABLED` name remains an
alias. It is independent of S3 and disabled by default. It currently archives
older **ground-truth rows only**; it is not the shared folder store, does not
hold AI output, and is not required for this pipeline.

If both are enabled, S3 updates immediately while DynamoDB only receives
finished events after `LOCAL_RETENTION_DAYS` and may then remove their local
SQLite/report data. Automatic DynamoDB cleanup pauses while any ground-truth
S3 marker is pending. Keep DynamoDB disabled during the initial S3 pilot unless
the team explicitly wants that retention behavior and has added the separate
DynamoDB IAM permissions documented in
[`../disaster_monitor-v5/README.md`](../disaster_monitor-v5/README.md#optional-secondary-tier-one-local-week-then-dynamodb).

Review candidates before enabling it:

```bash
cd disaster_monitor-v5
source ../deployment/local.env
.venv/bin/python -m disaster_monitor.archive_cli status
.venv/bin/python -m disaster_monitor.archive_cli run --dry-run
```

Only after reviewing that output should the team set
`DYNAMODB_ARCHIVE_ENABLED=true`. Startup logs contain a prominent warning when
the deletion-capable retention archive is active.

## Quick troubleshooting

| Error or symptom | Check |
| --- | --- |
| `NoCredentialsError` | Run `aws configure` and then `aws sts get-caller-identity` |
| `AccessDenied` | Confirm the IAM policy, account, bucket, and exact prefix |
| `NoSuchBucket` | Confirm the globally unique bucket name and AWS account |
| `S3_BUCKET is required` | Source `deployment/local.env` in this terminal |
| AI folder is missing | Check the worker log and local exact run for `.s3-uploaded.json` |
| Weather folder is missing | Check collector log and `disaster_monitor-v5/data/s3_pending/` |
