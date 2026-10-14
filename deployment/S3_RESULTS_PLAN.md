# Planned S3 archive for ground truth and AI results

This is a deployment plan, not active runtime behavior. The collector and
worker continue writing locally. Add S3 only after the v2 local layout has run
successfully under supervision.

## Cheapest simple starting point

Use one private S3 general-purpose bucket in the same AWS Region as the future
VM, with:

- Block Public Access enabled.
- Default Amazon S3 managed encryption (SSE-S3).
- No public website hosting.
- No cross-region replication.
- A billing budget and alert.
- S3 Standard storage initially. Revisit lifecycle tiers only after measuring
  real volume; this project produces many small files, for which transition and
  per-object charges can matter more than the storage itself.

Use a dedicated IAM role on an AWS VM. On a non-AWS host, use a dedicated IAM
user restricted to this one bucket and keep its credentials outside Git.

## Canonical object layout

S3 uses object-key prefixes rather than real folders. Use one event prefix so
official records and AI probes can be found together:

```text
s3://BUCKET/events/YYYY/Month/DD/EVENT_ID/
├── ground_truth/
│   └── collector event files
└── ai_probes/
    └── MESSAGE_ID/
        ├── AI_RESULTS.md
        ├── responses.json
        ├── trigger.raw.json
        ├── trigger.json
        ├── manifest.json
        ├── probes.jsonl
        └── raw/
```

Use the collector's `event_id` and each queue message's `message_id`; do not
attempt to match records by filename, title, or timestamp alone.

## Reliability requirements for the future uploader

1. Upload only closed files; never upload `.tmp` files.
2. Do not delete local data after upload.
3. Record each uploaded relative path, SHA-256, size, S3 key, ETag, and upload
   timestamp in a separate SQLite upload ledger.
4. Treat upload retries separately from AI retries. An S3 outage must not cause
   another paid AI probe.
5. Use deterministic keys so retries overwrite the same object rather than
   producing duplicates.
6. Verify object existence and size before marking an upload complete.
7. Add a backfill command for results collected before S3 was enabled.
8. Test with a separate bucket or prefix before enabling continuous uploads.

## Minimal manual pilot

After creating the bucket and configuring the AWS CLI, a manual backup of the
current local results can be tested with:

```bash
aws s3 sync pipeline_data/results/ \
  s3://BUCKET/pilot/ai-results/ \
  --exclude "*.tmp"
```

This pilot is only a backup test; it does not yet create the canonical unified
event prefixes above.

## Codex prompt for the later implementation

```text
In the TrackA-AI-NaturlaDisasters repository, implement an optional, durable S3
archive uploader without changing the collector-to-worker trigger contract or
causing paid AI probes to repeat. Read deployment/S3_RESULTS_PLAN.md and the
current v2 result layout first. Use boto3 and a separate SQLite upload ledger.
Map both ground-truth files and AI result cycles into deterministic keys under
events/YYYY/Month/DD/EVENT_ID/{ground_truth,ai_probes}/. Upload only completed
files, ignore .tmp files, retain all local files, store SHA-256/size/key/status,
retry uploads independently with backoff, and provide one-shot backfill plus
continuous modes. Credentials must come from the normal AWS credential chain,
never JSON or source code. Add mock-based tests that make no AWS calls, clear
console status, least-privilege IAM and bucket setup documentation, and a
dry-run command that prints every local-to-S3 mapping. Preserve all current
tests and research reproducibility fields. Make the work on a new branch and do
not merge or enable uploads automatically.
```
