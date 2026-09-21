# Emergency Alert Collector

A small Python collector for:
- National Weather Service (NWS) active weather alerts
- FEMA IPAWS archived alerts (non-weather and weather messages appearing in the archive)

The collector stores normalized alert information and the original JSON in a SQLite database.

## Why these sources?

NWS provides active alerts through `https://api.weather.gov/alerts/active`.

FEMA's IPAWS archive is an authoritative archive of Common Alerting Protocol (CAP) messages. FEMA publishes it with about a 24-hour delay, so it should be treated as an archive/ground-truth source rather than a live-alert feed.

## Project files

- `collector.py` - continuously collects both sources
- `database.py` - creates and writes the SQLite database
- `config.py` - settings
- `view_alerts.py` - simple readable command-line viewer
- `requirements.txt` - Python dependency
- `data/alerts.db` - created automatically when the collector first runs

## 1. Install

Python 3.10+ is recommended.

```bash
python -m venv .venv
```

Activate it:

macOS/Linux:
```bash
source .venv/bin/activate
```

Windows:
```powershell
.venv\Scripts\Activate.ps1
```

Then:

```bash
pip install -r requirements.txt
```

## 2. Configure the NWS user agent

Open `config.py` and replace:

```python
NWS_USER_AGENT = "EmergencyAlertCollector/1.0 your-email@example.com"
```

with your own contact information.

NWS asks clients to identify themselves with a User-Agent containing contact information.

## 3. Test one collection cycle

Run:

```bash
python collector.py --once
```

You should see how many NWS and FEMA records were collected.

## 4. View saved alerts

```bash
python view_alerts.py
```

Useful examples:

```bash
python view_alerts.py --source NWS --limit 20
python view_alerts.py --source FEMA --limit 20
python view_alerts.py --event "Tornado Warning"
python view_alerts.py --days 1
```

## 5. Run continuously

```bash
python collector.py
```

The default schedule is:
- NWS: every 60 seconds
- FEMA: every 15 minutes

The collector does not create a new copy every time an unchanged alert is seen. It uses the source identifier plus a content hash to save only new alert versions.

## Important storage decision

Keep `data/alerts.db`.

It is the main historical database.

The database stores the normalized fields plus the original source JSON. This means you can change the viewer or analysis code later without losing information.

For a Raspberry Pi, I recommend eventually putting the database on a USB SSD if you expect to keep years of data. For initial development, an SD card is fine.

## Current limitations

This first version is deliberately small.

It does not yet:
- send notifications
- provide a web dashboard
- download every historical FEMA record
- attempt to decide whether an alert is "true" or "important"
- predict disasters

It records what the government sources reported.

## Moving to the Raspberry Pi

Copy this entire folder to the Pi and run the same commands. Later, use a systemd service so the collector starts automatically when the Pi boots.
