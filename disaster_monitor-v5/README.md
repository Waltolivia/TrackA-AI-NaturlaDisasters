# Disaster Monitor v0.5

Always-on Python disaster monitor using **NWS** and **NASA EONET**. IPAWS has been removed.

## What v0.5 does

- Polls NWS (default 60 seconds) and NASA EONET (default 10 minutes).
- Stores raw/normalized alerts in SQLite and deduplicates repeated polls.
- Groups alerts into persistent disaster events, including CAP-reference matching and near-duplicate EONET matching.
- Separates the database event lifecycle (`ACTIVE`, `ENDED`, `COMPLETE`) from the operational alert phase (`WATCH`, `WARNING`, `IMMINENT`, `ACTIVE_CONFIRMED`, etc.).
- Suppresses downstream messages during each collector's first successful startup sync.
- Sends durable one-time JSON jobs for meaningful live changes only.
- Produces monthly human-readable indexes and detailed per-event text reports with unrestricted long NWS affected-area, description, instruction, and parameter sections.
- Maintains heartbeat health, rotating logs, SQLite backups, retry/backoff, and macOS launchd support.

## Downstream notification rules

A JSON job is created in `outbox/pending/` for:

- `NEW_EVENT`
- `STATUS_CHANGED`
- `SEVERITY_CHANGED` (severity escalation)
- `EVENT_ENDED`

No downstream job is created for:

- exact duplicates
- routine/non-meaningful revisions
- initial startup/backfill sync
- `COLLECTION_COMPLETE` (record/archive only by default)

Each job includes a unique `message_id`, stable `event_id`, disaster type/name/location, current operational status, lifecycle, severity, source, and change details. A consumer should move/claim a job to `processing/`, then acknowledge it to `completed/` or move it to `failed/`.

## Storage

```text
data/disaster_monitor.db        master/source-of-truth database
data/health.json                heartbeat/source health
archive/YYYY/MM/                human archive
archive/YYYY/MM/*_Events.txt    monthly event index
archive/YYYY/MM/events/*.txt    full individual event reports
outbox/pending/                 waiting downstream jobs
outbox/processing/              claimed jobs
outbox/completed/               successful jobs
outbox/failed/                  failed jobs
logs/disaster_monitor.log       rotating runtime log
backups/                        SQLite backups
```

## Install and test

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -v
```

Run manually:

```bash
python -m disaster_monitor.main
```

Stop cleanly with **Control+C**.

## Important configuration

Environment variables include:

```text
NWS_POLL_SECONDS=60
EONET_POLL_SECONDS=600
SUPPRESS_INITIAL_SYNC=true
DATABASE_PATH=data/disaster_monitor.db
OUTBOX_PATH=outbox
ARCHIVE_PATH=archive
END_GRACE_MINUTES=30
COLLECTION_GRACE_HOURS=24
```

## Operational phase derivation

The monitor derives a compact operational phase from normalized source fields. NWS urgency/certainty plus watch/warning terminology are used to distinguish phases such as `WATCH`, `WARNING`, `IMMINENT`, and `ACTIVE_CONFIRMED`. This is intentionally separate from the event lifecycle so a warning can still belong to an `ACTIVE` database event.

The original source record is always retained in SQLite and the detailed human report, so this derived phase does not replace source data.

## Queue CLI

See `python -m disaster_monitor.queue_cli --help` for queue-management commands available to a downstream consumer.

## macOS always-on installation

The `macos/` directory contains the launch-agent template and installer from the prior always-on release. Test the monitor manually before enabling automatic startup.
