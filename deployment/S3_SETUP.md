# Shared S3 research archive

S3 is the primary off-machine archive for this project. The collector and AI
worker use the same bucket and prefix, while local SQLite databases and files
remain the recoverable working copy.

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

## 1. Create the bucket

The easiest setup is in the AWS Console:

1. Open **S3 → Create bucket**.
2. Choose one globally unique name, such as
   `byu-tracka-disaster-study-ACCOUNT-NUMBER`.
3. Choose one region and use it everywhere. `us-west-2` is a reasonable Utah
   default.
4. Leave **Block all public access** enabled.
5. Enable **Bucket Versioning** so accidental overwrites can be recovered.
6. Leave default encryption enabled with **SSE-S3**.
7. Create the bucket. Do not add public website hosting or public bucket rules.

The application also requests SSE-S3 encryption on each upload.

## 2. Create uploader credentials

For local testing, create a dedicated IAM user or role with programmatic
access. Replace `YOUR_BUCKET` in this least-privilege policy:

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
          "s3:prefix": ["disaster_monitor-v5/archive/*"]
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

Team members who need to browse or download results should receive separate
read permissions through their own AWS identities. Do not share the uploader's
secret key in Git or place it in either repository `.env` file.

Install and configure the AWS CLI once on a development computer:

```bash
aws configure
aws sts get-caller-identity
```

`boto3` automatically uses that AWS profile. On an EC2 VM, prefer an instance
role with the policy above so no long-lived AWS secret is stored on disk.

## 3. Configure both processes

Use identical values in both terminals or both service environment files:

```bash
export S3_ARCHIVE_ENABLED=true
export S3_BUCKET='YOUR_BUCKET'
export S3_PREFIX='disaster_monitor-v5/archive'
export AWS_REGION='us-west-2'
```

Optional retry timing:

```bash
export S3_SYNC_SECONDS=5       # collector retry queue
export S3_RETRY_SECONDS=60     # AI worker retry scan
```

For `systemd`, put the shared values in both `/etc/tracka/collector.env` and
`/etc/tracka/providers.env`. Templates are under `deployment/systemd/`.

## 4. Verify before using paid models

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
mkdir -p local_test/outbox/{pending,processing,completed,failed}
cp pipeline_worker/examples/v5.flash-flood.json \
  local_test/outbox/pending/s3-test.json

uv run --project pipeline_worker pipeline-worker \
  --outbox local_test/outbox \
  --state-db local_test/worker.db \
  --output local_test/results \
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
remain until all ground-truth objects upload successfully.

## Failure behavior

- Local files are written before an S3 upload is attempted.
- Collector uploads are queued in `disaster_monitor-v5/data/s3_pending/` and
  retried without losing the event.
- A completed AI cycle gets `.s3-uploaded.json` only after all S3 objects are
  accepted.
- Missing AI upload markers are retried independently of AI probing. An S3
  outage does not repeat completed paid API requests.
- Uploading deterministic keys is idempotent. Repeating an interrupted upload
  safely replaces the same current snapshot.

## DynamoDB compatibility

The teammate's DynamoDB tiered archive remains available through
`AWS_ARCHIVE_ENABLED`. It is independent of S3 and is disabled by default.
S3 should be enabled for the shared research files. DynamoDB may later be used
as a searchable metadata index, but it is not required for this pipeline.

If both are enabled, S3 updates immediately while DynamoDB only receives
finished events after `LOCAL_RETENTION_DAYS` and may then remove their local
SQLite/report data. Keep DynamoDB disabled during the initial S3 pilot unless
the team explicitly wants that retention behavior.
