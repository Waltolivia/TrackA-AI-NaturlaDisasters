# Disaster Monitor v0.2

> **Legacy:** Retained for reproducibility and flat-outbox compatibility only.
> Use `../../disaster_monitor-v5/` for the active pipeline.

A Python polling service that collects natural-disaster records, keeps raw source messages, deduplicates repeated polls, groups related records into incidents, detects escalation, tracks incident lifecycle, and writes JSON jobs for a future AI Prompter.

## Sources and polling
- NWS active alerts: 60 seconds by default.
- NASA EONET open events: 10 minutes by default.
- IPAWS: adapter placeholder until feed/access details are known.
- Failed requests use exponential backoff rather than rapid retries.

## v0.2 matching engine
Matching is intentionally confidence-based. Strong relationships are accepted automatically; uncertain fuzzy matches are not silently merged.

Signals include:
1. CAP/source alert references to an already stored alert (strongest NWS relationship).
2. Stable upstream event IDs, such as an EONET event ID.
3. Canonical disaster type.
4. County/area text overlap.
5. Geometry/coordinate proximity when geometry is available.
6. Time proximity.

High-confidence matches join the existing event. Medium-confidence candidates are preserved as separate events and recorded in `review_queue`, preventing an uncertain match from corrupting an existing incident. Low-confidence records become new events.

## v0.2 lifecycle
Events have three operational lifecycle states:
- `ACTIVE`: incoming/current incident.
- `ENDED`: explicit end/cancel/expiry, or the most recent alert has remained expired beyond `END_GRACE_MINUTES`.
- `COMPLETE`: the event has remained ended for `COLLECTION_GRACE_HOURS`, giving late enrichment (including future IPAWS data) time to arrive.

The JSON outbox now supports:
- `NEW_EVENT`
- `ESCALATION`
- `EVENT_ENDED`
- `COLLECTION_COMPLETE`

Each lifecycle notification is emitted only once. If a matching update arrives while an event is `ENDED`, it can reactivate the event before completion.

**Important:** `COLLECTION_COMPLETE` means this collector's configured waiting period has elapsed. It is not a scientific assertion that no further information can ever arrive.

## Data safety
Every accepted raw source record is retained in SQLite. `(source, source_id)` and source-content hashes prevent duplicates. Grouping records into an event does not overwrite the originals.

## Install
Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export NWS_USER_AGENT='MyDisasterMonitor/0.2 (contact@example.org)'
python -m disaster_monitor.main
```

## Configuration
- `NWS_POLL_SECONDS=60`
- `EONET_POLL_SECONDS=600`
- `NWS_USER_AGENT=...`
- `DATABASE_PATH=data/disaster_monitor.db`
- `OUTBOX_PATH=outbox`
- `REQUEST_TIMEOUT_SECONDS=20`
- `EONET_DAYS=30`
- `LIFECYCLE_POLL_SECONDS=60`
- `END_GRACE_MINUTES=30`
- `COLLECTION_GRACE_HOURS=24`

For your planned IPAWS behavior, `COLLECTION_GRACE_HOURS=24` is the initial default. Increase it if the feed you eventually connect can arrive later than that.

## Tests
```bash
python -m pytest -q
```

Tests cover duplicate suppression, CAP-reference event matching, escalation, ending an event, collection completion, and ensuring lifecycle notifications only fire once.

## IPAWS
`disaster_monitor/collectors/ipaws.py` remains a deliberate adapter placeholder. Once the exact IPAWS feed/API credentials and delivery format are known, it can normalize records into `NormalizedAlert`; the database, matcher, lifecycle, and JSON prompter do not need to be redesigned.

## Operational note
This is a collection/workflow service, not an official life-safety warning system and should not be the sole source for emergency decisions.
