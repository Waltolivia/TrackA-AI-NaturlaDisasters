import argparse
import time
from datetime import datetime, timedelta, timezone

import requests

from config import (
    FEMA_INTERVAL_SECONDS, FEMA_LOOKBACK_HOURS, FEMA_PAGE_SIZE, FEMA_URL,
    NWS_INTERVAL_SECONDS, NWS_URL, NWS_USER_AGENT
)
from database import initialize_database, latest_fema_sent, save_alert

session = requests.Session()
session.headers.update({
    "User-Agent": NWS_USER_AGENT,
    "Accept": "application/geo+json, application/json",
})


def get_json(url, params=None):
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def collect_nws():
    data = get_json(NWS_URL)
    count = 0

    for feature in data.get("features", []):
        p = feature.get("properties", {})
        source_id = feature.get("id") or p.get("id")
        if not source_id:
            continue

        if save_alert(
            source="NWS",
            source_id=source_id,
            sent=p.get("sent"),
            effective=p.get("effective"),
            onset=p.get("onset"),
            expires=p.get("expires"),
            status=p.get("status"),
            message_type=p.get("messageType"),
            event=p.get("event"),
            headline=p.get("headline"),
            severity=p.get("severity"),
            urgency=p.get("urgency"),
            certainty=p.get("certainty"),
            sender=p.get("sender"),
            sender_name=p.get("senderName"),
            area=p.get("areaDesc"),
            description=p.get("description"),
            instruction=p.get("instruction"),
            web_url=p.get("web"),
            raw_data=feature,
        ):
            count += 1

    return count


def arcgis_date(value):
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
    return str(value)


def collect_fema():
    latest = latest_fema_sent()
    if latest:
        try:
            start = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            start -= timedelta(hours=FEMA_LOOKBACK_HOURS)
        except ValueError:
            start = datetime.now(timezone.utc) - timedelta(hours=FEMA_LOOKBACK_HOURS)
    else:
        start = datetime.now(timezone.utc) - timedelta(hours=FEMA_LOOKBACK_HOURS)

    total = 0
    offset = 0

    while True:
        params = {
            "where": f"sent >= TIMESTAMP '{start.strftime('%Y-%m-%d %H:%M:%S')}'",
            "outFields": "*",
            "returnGeometry": "false",
            "orderByFields": "sent ASC",
            "resultOffset": offset,
            "resultRecordCount": FEMA_PAGE_SIZE,
            "f": "json",
        }

        data = get_json(FEMA_URL, params=params)
        features = data.get("features", [])

        for feature in features:
            f = feature.get("attributes", {})
            source_id = f.get("identifier") or f.get("id") or str(f.get("objectid"))
            if not source_id:
                continue

            if save_alert(
                source="FEMA",
                source_id=source_id,
                sent=arcgis_date(f.get("sent")),
                effective=arcgis_date(f.get("info_effective")),
                onset=arcgis_date(f.get("info_onset")),
                expires=arcgis_date(f.get("info_expires")),
                status=f.get("status"),
                message_type=f.get("msgtype"),
                event=f.get("info_event"),
                headline=f.get("info_headline"),
                severity=f.get("info_severity"),
                urgency=f.get("info_urgency"),
                certainty=f.get("info_certainty"),
                sender=f.get("sender"),
                sender_name=f.get("info_sendername"),
                area=f.get("info_area_areadesc") or f.get("area_areadesc"),
                description=f.get("info_description"),
                instruction=f.get("info_instruction"),
                web_url=f.get("info_web"),
                raw_data=f,
            ):
                total += 1

        if len(features) < FEMA_PAGE_SIZE:
            break
        offset += len(features)

    return total


def run_once():
    initialize_database()

    print("Collecting NWS alerts...")
    try:
        print(f"NWS: {collect_nws()} new disaster alert version(s)")
    except Exception as error:
        print(f"NWS ERROR: {error}")

    print("Collecting FEMA IPAWS archive...")
    try:
        print(f"FEMA: {collect_fema()} new disaster alert version(s)")
    except Exception as error:
        print(f"FEMA ERROR: {error}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    initialize_database()

    if args.once:
        run_once()
        return

    print("Emergency Disaster Alert Collector started.")
    print("Only natural-disaster/dangerous-natural-event alerts are saved.")
    print("Press Ctrl+C to stop.")

    last_nws = 0
    last_fema = 0

    while True:
        now = time.monotonic()

        if now - last_nws >= NWS_INTERVAL_SECONDS:
            try:
                print(f"\nNWS: {collect_nws()} new disaster alert version(s)")
            except Exception as error:
                print(f"NWS ERROR: {error}")
            last_nws = time.monotonic()

        if now - last_fema >= FEMA_INTERVAL_SECONDS:
            try:
                print(f"FEMA: {collect_fema()} new disaster alert version(s)")
            except Exception as error:
                print(f"FEMA ERROR: {error}")
            last_fema = time.monotonic()

        time.sleep(1)


if __name__ == "__main__":
    main()
