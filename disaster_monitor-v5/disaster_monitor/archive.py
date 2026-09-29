import calendar
import json
import re
import textwrap
from pathlib import Path
from datetime import datetime, timedelta


def _dt(v):
    if not v:
        return None

    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe(s):
    return (
        re.sub(r"[^A-Za-z0-9._-]+", "-", str(s or "event"))
        .strip("-")[:80]
        or "event"
    )


def _wrap(text, width=112):
    if not text:
        return "N/A"

    return "\n".join(
        textwrap.fill(
            p,
            width=width,
            replace_whitespace=False
        )
        if p.strip()
        else ""
        for p in str(text).splitlines()
    )


def _raw(alert):
    try:
        return json.loads(alert["raw_json"])
    except Exception:
        return {}


def _nws_fields(raw):
    p = raw.get("properties") or {}
    params = p.get("parameters") or {}

    def val(*names):
        for n in names:
            x = p.get(n)
            if x:
                return x
        return None

    return {
        "description": val("description"),
        "instruction": val("instruction"),
        "area": val("areaDesc"),
        "sender": val("senderName", "sender"),
        "parameters": params,
    }


def _month_folder(when, root):
    """
    Return the human-readable month folder.

    Example:
        archive/2026/September
    """
    return (
        Path(root)
        / f"{when.year:04d}"
        / when.strftime("%B")
    )


def _week_folder_name(when):
    """
    Return the Monday-Sunday calendar week containing `when`,
    clipped so the folder never extends outside the month.

    Example for September 28, 2026:
        Sep_28-Sep_30
    """

    month_start = when.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    last_day = calendar.monthrange(
        when.year,
        when.month
    )[1]

    month_end = when.replace(
        day=last_day,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    # Monday = 0, Sunday = 6
    week_start = when - timedelta(days=when.weekday())
    week_end = week_start + timedelta(days=6)

    # Do not allow a week's folder name to cross
    # outside the current month.
    if week_start < month_start:
        week_start = month_start

    if week_end > month_end:
        week_end = month_end

    start_label = week_start.strftime("%b_%d")
    end_label = week_end.strftime("%b_%d")

    return f"{start_label}-{end_label}"


def render_event(db, event_id, root="archive"):
    event = db.get_event(event_id)
    alerts = db.alerts_for_event(event_id)

    opened = _dt(event["opened_at"])

    if opened:
        month_folder = _month_folder(opened, root)
        week_folder = month_folder / _week_folder_name(opened)
    else:
        month_folder = Path(root) / "unknown" / "Unknown"
        week_folder = month_folder / "Unknown_Dates"

    week_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    name = _safe(
        event["title"]
        if event["title"]
        else event["canonical_type"]
    )

    path = week_folder / (
        f'{event["public_id"]}_{name}.txt'
    )

    lines = [
        "=" * 120,
        "DISASTER EVENT REPORT",
        "=" * 120,
        "",
        (
            f'Event: {event["public_id"]}    '
            f'Type: {event["canonical_type"]}    '
            f'Phase: {event["operational_phase"]}    '
            f'Lifecycle: {event["status"]}    '
            f'Highest Severity: '
            f'{event["severity"] or "Unknown"}'
        ),
        (
            f'Started: {event["opened_at"]}    '
            f'Last Seen: {event["last_seen_at"]}    '
            f'Ended: {event["ended_at"] or "N/A"}'
        ),
        (
            f'Primary Location: '
            f'{event["area_desc"] or "N/A"}'
        ),
        "",
        "EVENT HISTORY",
        "=" * 120,
    ]

    for i, a in enumerate(alerts, 1):
        raw = _raw(a)

        nf = (
            _nws_fields(raw)
            if a["source"] == "NWS"
            else {}
        )

        lines += [
            "",
            (
                f'[{i:02d}] '
                f'{a["sent_at"] or a["observed_at"]}    '
                f'{a["source"]}    '
                f'{a["event_type"]}    '
                f'{a["severity"] or "Unknown"}'
            ),
            "-" * 120,
            f'Headline: {a["headline"] or "N/A"}',
            (
                f'Expires: {a["expires_at"] or "N/A"}    '
                f'Urgency: {a["urgency"] or "N/A"}    '
                f'Certainty: {a["certainty"] or "N/A"}'
            ),
            "",
            "AFFECTED AREAS",
            "-" * 120,
            _wrap(
                nf.get("area")
                or a["area_desc"]
            ),
        ]

        if nf.get("description"):
            lines += [
                "",
                "DESCRIPTION",
                "-" * 120,
                _wrap(nf["description"]),
            ]

        if nf.get("instruction"):
            lines += [
                "",
                "INSTRUCTIONS",
                "-" * 120,
                _wrap(nf["instruction"]),
            ]

        if nf.get("parameters"):
            lines += [
                "",
                "ADDITIONAL NWS PARAMETERS",
                "-" * 120,
                _wrap(
                    json.dumps(
                        nf["parameters"],
                        indent=2,
                        ensure_ascii=False,
                    )
                ),
            ]

        lines += [
            "",
            "SOURCE",
            "-" * 120,
            (
                f'Source: {a["source"]}    '
                f'Source Alert ID: {a["source_id"]}'
            ),
        ]

    lines += [
        "",
        "=" * 120,
        "SOURCE SUMMARY",
        "=" * 120,
    ]

    counts = {}

    for a in alerts:
        counts[a["source"]] = (
            counts.get(a["source"], 0) + 1
        )

    lines.append(
        "    ".join(
            f"{k}: {v}"
            for k, v in sorted(counts.items())
        )
        or "No source records"
    )

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    render_month_index(
        db,
        opened,
        root,
    )

    return path


def render_month_index(db, when, root="archive"):
    if not when:
        return None

    events = db.events_opened_in_month(
        when.year,
        when.month,
    )

    folder = _month_folder(
        when,
        root,
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = folder / (
        f'{when.strftime("%B_%Y")}_Events.txt'
    )

    lines = [
        "=" * 120,
        (
            f'{when.strftime("%B %Y").upper()} '
            "- DISASTER EVENT INDEX"
        ),
        "=" * 120,
        "",
        (
            f'{"EVENT ID":<14} '
            f'{"STARTED":<20} '
            f'{"TYPE":<20} '
            f'{"SEVERITY":<10} '
            f'{"STATUS":<10} '
            f'{"WEEK":<17} '
            "LOCATION / NAME"
        ),
        "-" * 120,
    ]

    totals = {}

    for e in events:
        d = _dt(e["opened_at"])

        started = (
            d.strftime("%Y-%m-%d %H:%M")
            if d
            else e["opened_at"][:19]
        )

        loc = (
            e["area_desc"]
            or e["title"]
            or ""
        )

        week = (
            _week_folder_name(d)
            if d
            else "Unknown"
        )

        lines.append(
            f'{e["public_id"]:<14} '
            f'{started:<20} '
            f'{e["canonical_type"][:20]:<20} '
            f'{(e["severity"] or "Unknown")[:10]:<10} '
            f'{e["status"]:<10} '
            f'{week:<17} '
            f'{loc}'
        )

        totals[e["canonical_type"]] = (
            totals.get(
                e["canonical_type"],
                0
            ) + 1
        )

    lines += [
        "",
        "-" * 120,
        f"Total events: {len(events)}",
        "    ".join(
            f"{k}: {v}"
            for k, v in sorted(totals.items())
        ),
    ]

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return path
