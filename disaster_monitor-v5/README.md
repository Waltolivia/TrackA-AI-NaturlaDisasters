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


## Experiment and Formatting

When the test is run on terminal it looks like
``` text
2026-09-28 14:44:23,900 INFO disaster-monitor Disaster Monitor started
2026-09-28 14:44:23,911 INFO disaster-monitor database backup created backups/disaster_monitor_20260928T204423Z.db
2026-09-28 14:44:24,068 INFO httpx HTTP Request: GET https://api.weather.gov/alerts/active "HTTP/1.1 200 OK"
2026-09-28 14:44:24,852 INFO disaster-monitor NWS poll OK received=264 results={'filtered': 203, 'NEW_EVENT': 61} initial_sync=True
2026-09-28 14:44:24,945 INFO httpx HTTP Request: GET https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=30 "HTTP/1.1 200 OK"
2026-09-28 14:44:25,801 INFO disaster-monitor NASA_EONET poll OK received=72 results={'NEW_EVENT': 54, 'filtered': 13, 'ROUTINE_UPDATE': 5} initial_sync=True
2026-09-28 14:45:25,259 INFO httpx HTTP Request: GET https://api.weather.gov/alerts/active "HTTP/1.1 200 OK"
2026-09-28 14:45:25,345 INFO disaster-monitor NWS poll OK received=263 results={'filtered': 202, 'duplicate': 61} initial_sync=False
2026-09-28 14:46:25,731 INFO httpx HTTP Request: GET https://api.weather.gov/alerts/active "HTTP/1.1 200 OK"
2026-09-28 14:46:25,828 INFO disaster-monitor NWS poll OK received=263 results={'filtered': 202, 'duplicate': 61} initial_sync=False
2026-09-28 14:47:26,152 INFO httpx HTTP Request: GET https://api.weather.gov/alerts/active "HTTP/1.1 200 OK"
2026-09-28 14:47:26,240 INFO disaster-monitor NWS poll OK received=263 results={'filtered': 202, 'duplicate': 61} initial_sync=False
2026-09-28 14:48:26,588 INFO httpx HTTP Request: GET https://api.weather.gov/alerts/active "HTTP/1.1 200 OK"
2026-09-28 14:48:26,671 INFO disaster-monitor NWS poll OK received=263 results={'filtered': 202, 'duplicate': 61} initial_sync=False
2026-09-28 14:49:27,137 INFO httpx HTTP Request: GET https://api.weather.gov/alerts/active "HTTP/1.1 200 OK"
2026-09-28 14:49:27,242 INFO disaster-monitor NWS poll OK received=263 results={'filtered': 202, 'duplicate': 61} initial_sync=False
2026-09-28 14:50:27,690 INFO httpx HTTP Request: GET https://api.weather.gov/alerts/active "HTTP/1.1 200 OK"
2026-09-28 14:50:27,774 INFO disaster-monitor NWS poll OK received=263 results={'filtered': 202, 'duplicate': 61} initial_sync=False
^C2026-09-28 14:50:46,537 INFO disaster-monitor shutdown requested
2026-09-28 14:50:46,538 INFO disaster-monitor Disaster Monitor stopped cleanly
```

and when the info is saved it is saved by month, with a summery doument at the beggining, and indivudual even types (by event tag) saved with more data.

Example for Detailed Data:

``` text
========================================================================================================================
DISASTER EVENT REPORT
========================================================================================================================

Event: EVT-00000001    Type: flood    Phase: WATCH    Lifecycle: ACTIVE    Highest Severity: Severe
Started: 2026-09-28T20:44:24.136094+00:00    Last Seen: 2026-09-28T20:44:24.136094+00:00    Ended: N/A
Primary Location: Upper Gila River Valley; Southern Gila Foothills/Mimbres Valley; Southwest Desert/Lower Gila River Valley; Lowlands of the Bootheel; Uplands of the Bootheel; Southwest Desert/Mimbres Basin; Eastern Black Range Foothills; Sierra County Lakes; Northern Dona Ana County; Southern Dona Ana County/Mesilla Valley; West Slopes Sacramento Mountains Below 7500 Feet; Sacramento Mountains Above 7500 Feet; East Slopes Sacramento Mountains Below 7500 Feet; Otero Mesa; Central Grant County/Silver City Area; Southern Gila Region Highlands/Black Range; West Central Tularosa Basin/White Sands; East Central Tularosa Basin/Alamogordo; Southeast Tularosa Basin; Western El Paso County; Eastern/Central El Paso County; Northern Hudspeth Highlands/Hueco Mountains; Salt Basin; Southern Hudspeth Highlands; Rio Grande Valley of Eastern El Paso/Western Hudspeth Counties; Rio Grande Valley of Eastern Hudspeth County

EVENT HISTORY
========================================================================================================================

[01] 2026-09-28T14:30:00-06:00    NWS    Flood Watch    Severe
------------------------------------------------------------------------------------------------------------------------
Headline: Flood Watch issued September 28 at 2:30PM MDT until September 30 at 6:00AM MDT by NWS El Paso Tx/Santa Teresa NM
Expires: 2026-09-29T00:00:00-06:00    Urgency: Future    Certainty: Possible

AFFECTED AREAS
------------------------------------------------------------------------------------------------------------------------
Upper Gila River Valley; Southern Gila Foothills/Mimbres Valley; Southwest Desert/Lower Gila River Valley;
Lowlands of the Bootheel; Uplands of the Bootheel; Southwest Desert/Mimbres Basin; Eastern Black Range
Foothills; Sierra County Lakes; Northern Dona Ana County; Southern Dona Ana County/Mesilla Valley; West Slopes
Sacramento Mountains Below 7500 Feet; Sacramento Mountains Above 7500 Feet; East Slopes Sacramento Mountains
Below 7500 Feet; Otero Mesa; Central Grant County/Silver City Area; Southern Gila Region Highlands/Black Range;
West Central Tularosa Basin/White Sands; East Central Tularosa Basin/Alamogordo; Southeast Tularosa Basin;
Western El Paso County; Eastern/Central El Paso County; Northern Hudspeth Highlands/Hueco Mountains; Salt Basin;
Southern Hudspeth Highlands; Rio Grande Valley of Eastern El Paso/Western Hudspeth Counties; Rio Grande Valley
of Eastern Hudspeth County

DESCRIPTION
------------------------------------------------------------------------------------------------------------------------
* WHAT...Flooding caused by excessive rainfall continues to be
possible.

* WHERE...Southwest New Mexico including Dona Ana, Otero, Luna,
Sierra, Grant, and Hidalgo Counties. Far West Texas, including El
Paso and Hudspeth Counties.

* WHEN...Through late Tuesday night.

* IMPACTS...Excessive runoff may result in flooding of rivers,
creeks, streams, and other low-lying and flood-prone locations.
Low-water crossings may be flooded.

* ADDITIONAL DETAILS...
- Tropical moisture will be transported northward ahead of a
decaying Tropical Cyclone Polo today and tomorrow, bringing
widespread showers and thunderstorms to the region. High rainfall
rates and repeated rounds of rain up to 4 inches may result in
instances of flash flooding. Heavy rainfall from last week has
saturated soils and will elevate the flood threat further into
Wednesday morning.
- http://www.weather.gov/safety/flood

INSTRUCTIONS
------------------------------------------------------------------------------------------------------------------------
You should monitor later forecasts and be alert for possible Flood
Warnings. Those living in areas prone to flooding should be prepared
to take action should flooding develop.

ADDITIONAL NWS PARAMETERS
------------------------------------------------------------------------------------------------------------------------
{
  "AWIPSidentifier": [
    "FFAEPZ"
  ],
  "BLOCKCHANNEL": [
    "EAS",
    "NWEM",
    "CMAS"
  ],
  "EAS-ORG": [
    "WXR"
  ],
  "NWSheadline": [
    "FLOOD WATCH REMAINS IN EFFECT THROUGH LATE TUESDAY NIGHT"
  ],
  "VTEC": [
    "/O.CON.KEPZ.FA.A.0017.000000T0000Z-260930T1200Z/"
  ],
  "WMOidentifier": [
    "WGUS64 KEPZ 282030"
  ],
  "eventEndingTime": [
    "2026-09-30T06:00:00-06:00"
  ],
  "expiredReferences": [
    "w-nws.webmaster@noaa.gov,urn:oid:2.49.0.1.840.0.944aac699838c04208567544f2765931b58d56e4.001.1,2026-09-
27T22:00:00-06:00 w-
nws.webmaster@noaa.gov,urn:oid:2.49.0.1.840.0.9e80750afc87793cb4ea5648524e88d37e4ebd77.001.1,2026-09-
27T13:00:00-06:00 w-
nws.webmaster@noaa.gov,urn:oid:2.49.0.1.840.0.41485c46e9e1666557bf6f7e64572be019ff50c6.001.1,2026-09-
26T23:55:00-06:00"
  ]
}

SOURCE
------------------------------------------------------------------------------------------------------------------------
Source: NWS    Source Alert ID: urn:oid:2.49.0.1.840.0.e453dfd0dde76e74c64738d5eaf4925051082da9.001.1

========================================================================================================================
SOURCE SUMMARY
========================================================================================================================
NWS: 1
```
