import argparse
import time
from datetime import datetime, timedelta, timezone

import requests

from config import (
    FEMA_INTERVAL_SECONDS,
    FEMA_LOOKBACK_HOURS,
    FEMA_PAGE_SIZE,
    FEMA_URL,
    NWS_INTERVAL_SECONDS,
    NWS_URL,
    NWS_USER_AGENT,
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
        properties = feature.get("properties", {})
        source_id = feature.get("id") or properties.get("id")

        if not source_id:
            continue

        saved = save_alert(
            source="NWS",
            source_id=source_id,
            sent=properties.get("sent"),
            effective=properties.get("effective"),
            onset=properties.get("onset"),
            expires=properties.get("expires"),
            status=properties.get("status"),
            message_type=properties.get("messageType"),
            event=properties.get("event"),
            headline=properties.get("headline"),
            severity=properties.get("severity"),
            urgency=properties.get("urgency"),
            certainty=properties.get("certainty"),
            sender=properties.get("sender"),
            sender_name=properties.get("senderName"),
            area=properties.get("areaDesc"),
            description=properties.get("description"),
            instruction=properties.get("instruction"),
            web_url=properties.get("web"),
            raw_data=feature,
        )

        if saved:
            count += 1

    return count


def collect_fema():
    # FEMA's archive is delayed, so use a rolling window rather than asking
    # for only records after the last successful request.
    latest = latest_fema_sent()

    if latest:
        try:
            start = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            start -= timedelta(hours=FEMA_LOOKBACK_HOURS)
        except ValueError:
            start = datetime.now(timezone.utc) - timedelta(hours=FEMA_LOOKBACK_HOURS)
    else:
        start = datetime.now(timezone.utc) - timedelta(hours=FEMA_LOOKBACK_HOURS)

    start_ms = int(start.timestamp() * 1000)

    total_saved = 0
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
            fields = feature.get("attributes", {})

            source_id = (
                fields.get("identifier")
                or fields.get("id")
                or str(fields.get("objectid"))
            )

            if not source_id:
                continue

            # ArcGIS dates are normally Unix milliseconds.
            sent = arcgis_date(fields.get("sent"))
            effective = arcgis_date(fields.get("info_effective"))
            onset = arcgis_date(fields.get("info_onset"))
            expires = arcgis_date(fields.get("info_expires"))

            saved = save_alert(
                source="FEMA",
                source_id=source_id,
                sent=sent,
                effective=effective,
                onset=onset,
                expires=expires,
                status=fields.get("status"),
                message_type=fields.get("msgtype"),
                event=fields.get("info_event"),
                headline=fields.get("info_headline"),
                severity=fields.get("info_severity"),
                urgency=fields.get("info_urgency"),
                certainty=fields.get("info_certainty"),
                sender=fields.get("sender"),
                sender_name=fields.get("info_sendername"),
                area=fields.get("info_area_areadesc") or fields.get("area_areadesc"),
                description=fields.get("info_description"),
                instruction=fields.get("info_instruction"),
                web_url=fields.get("info_web"),
                raw_data=fields,
            )

            if saved:
                total_saved += 1

        if len(features) < FEMA_PAGE_SIZE:
            break

        offset += len(features)

    return total_saved


def arcgis_date(value):
    if value in (None, "", 0):
        return None

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(
            value / 1000,
            tz=timezone.utc
        ).isoformat()

    return str(value)


def run_once():
    initialize_database()

    print("Collecting NWS alerts...")
    try:
        nws_count = collect_nws()
        print(f"NWS: {nws_count} new alert version(s)")
    except Exception as error:
        print(f"NWS ERROR: {error}")

    print("Collecting FEMA IPAWS archive...")
    try:
        fema_count = collect_fema()
        print(f"FEMA: {fema_count} new alert version(s)")
    except Exception as error:
        print(f"FEMA ERROR: {error}")

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one collection cycle and exit."
    )
    args = parser.parse_args()

    initialize_database()

    if args.once:
        run_once()
        return

    last_nws = 0
    last_fema = 0

    print("Emergency Alert Collector started.")
    print("Press Ctrl+C to stop.")

    while True:
        now = time.monotonic()

        if now - last_nws >= NWS_INTERVAL_SECONDS:
            print("\n--- NWS collection ---")
            try:
                count = collect_nws()
                print(f"NWS: {count} new alert version(s)")
            except Exception as error:
                print(f"NWS ERROR: {error}")

            last_nws = time.monotonic()

        if now - last_fema >= FEMA_INTERVAL_SECONDS:
            print("\n--- FEMA collection ---")
            try:
                count = collect_fema()
                print(f"FEMA: {count} new alert version(s)")
            except Exception as error:
                print(f"FEMA ERROR: {error}")

            last_fema = time.monotonic()

        time.sleep(1)


if __name__ == "__main__":
    main()
