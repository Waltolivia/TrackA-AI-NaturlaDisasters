import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DATABASE_PATH, DISASTER_KEYWORDS, NON_DISASTER_KEYWORDS


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def initialize_database():
    with get_connection() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                sent TEXT,
                effective TEXT,
                onset TEXT,
                expires TEXT,
                status TEXT,
                message_type TEXT,
                event TEXT,
                headline TEXT,
                severity TEXT,
                urgency TEXT,
                certainty TEXT,
                sender TEXT,
                sender_name TEXT,
                area TEXT,
                description TEXT,
                instruction TEXT,
                web_url TEXT,
                raw_json TEXT NOT NULL,
                UNIQUE(source, source_id, version_hash)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_collected ON alerts(collected_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_source ON alerts(source)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_event ON alerts(event)")
        db.commit()


def is_disaster_alert(event=None, headline=None, description=None, instruction=None):
    text = " ".join(
        x or "" for x in [event, headline, description, instruction]
    ).lower()

    has_disaster = any(k.lower() in text for k in DISASTER_KEYWORDS)
    has_non_disaster = any(k.lower() in text for k in NON_DISASTER_KEYWORDS)

    if not has_disaster:
        return False

    # A natural-hazard match is required. This means an ordinary
    # "local area emergency" or missing-child alert is rejected.
    # A natural-hazard alert containing "evacuation" is still kept.
    return True


def version_hash(data):
    encoded = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def save_alert(source, source_id, sent=None, effective=None, onset=None,
               expires=None, status=None, message_type=None, event=None,
               headline=None, severity=None, urgency=None, certainty=None,
               sender=None, sender_name=None, area=None, description=None,
               instruction=None, web_url=None, raw_data=None):

    raw_data = raw_data or {}

    if not is_disaster_alert(event, headline, description, instruction):
        return False

    digest = version_hash(raw_data)

    with get_connection() as db:
        cursor = db.execute("""
            INSERT OR IGNORE INTO alerts (
                source, source_id, version_hash, collected_at, sent,
                effective, onset, expires, status, message_type, event,
                headline, severity, urgency, certainty, sender,
                sender_name, area, description, instruction, web_url, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source, source_id, digest, utc_now(), sent, effective, onset,
            expires, status, message_type, event, headline, severity,
            urgency, certainty, sender, sender_name, area, description,
            instruction, web_url, json.dumps(raw_data, ensure_ascii=False)
        ))
        db.commit()
        return cursor.rowcount == 1


def latest_fema_sent():
    with get_connection() as db:
        row = db.execute(
            "SELECT MAX(sent) AS latest FROM alerts WHERE source='FEMA'"
        ).fetchone()
        return row["latest"] if row and row["latest"] else None


def get_recent(limit=20, source=None, event=None, days=None):
    query = "SELECT * FROM alerts WHERE 1=1"
    params = []

    if source:
        query += " AND source=?"
        params.append(source)
    if event:
        query += " AND event LIKE ?"
        params.append("%" + event + "%")
    if days is not None:
        query += " AND collected_at >= datetime('now', ?)"
        params.append(f"-{int(days)} days")

    query += " ORDER BY collected_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as db:
        return db.execute(query, params).fetchall()
