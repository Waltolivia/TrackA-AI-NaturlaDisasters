import json, sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA='''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, public_id TEXT UNIQUE, canonical_type TEXT NOT NULL, title TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'ACTIVE', severity TEXT, area_desc TEXT, opened_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
 ended_at TEXT, collection_complete_at TEXT, notified_start INTEGER NOT NULL DEFAULT 0, notified_end INTEGER NOT NULL DEFAULT 0,
 notified_complete INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, source_id TEXT NOT NULL, content_hash TEXT NOT NULL, event_id INTEGER,
 event_type TEXT, headline TEXT, severity TEXT, urgency TEXT, certainty TEXT, status TEXT, sent_at TEXT, expires_at TEXT, area_desc TEXT,
 geometry_json TEXT, raw_json TEXT NOT NULL, observed_at TEXT NOT NULL,
 UNIQUE(source, source_id), UNIQUE(source, content_hash), FOREIGN KEY(event_id) REFERENCES events(id)
);
CREATE TABLE IF NOT EXISTS source_links (source TEXT NOT NULL, source_event_id TEXT NOT NULL, event_id INTEGER NOT NULL,
 UNIQUE(source, source_event_id), FOREIGN KEY(event_id) REFERENCES events(id));
CREATE TABLE IF NOT EXISTS review_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, source_id TEXT, candidate_event_id INTEGER,
 confidence REAL, reason TEXT, created_at TEXT, resolved INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_events_status_type ON events(status,canonical_type);
CREATE INDEX IF NOT EXISTS idx_alerts_event ON alerts(event_id);
'''

class Database:
    def __init__(self,path:str):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            # Lightweight migration for v0.1 databases.
            cols={r['name'] for r in db.execute('PRAGMA table_info(events)')}
            for name,definition in [('collection_complete_at','TEXT'),('notified_complete','INTEGER NOT NULL DEFAULT 0')]:
                if name not in cols: db.execute(f'ALTER TABLE events ADD COLUMN {name} {definition}')
            acols={r['name'] for r in db.execute('PRAGMA table_info(alerts)')}
            if 'geometry_json' not in acols: db.execute('ALTER TABLE alerts ADD COLUMN geometry_json TEXT')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try: yield db; db.commit()
        finally: db.close()
    def seen(self,source,source_id,content_hash):
        with self.connect() as db:return db.execute('SELECT id,event_id FROM alerts WHERE source=? AND (source_id=? OR content_hash=?)',(source,source_id,content_hash)).fetchone()
    def find_alert_by_source_id(self,source,source_id):
        with self.connect() as db:return db.execute('SELECT * FROM alerts WHERE source=? AND source_id=?',(source,source_id)).fetchone()
    def create_event(self,canonical_type,title,severity,area_desc,now):
        with self.connect() as db:
            cur=db.execute('INSERT INTO events(public_id,canonical_type,title,severity,area_desc,opened_at,last_seen_at) VALUES(NULL,?,?,?,?,?,?)',(canonical_type,title,severity,area_desc,now,now)); eid=cur.lastrowid
            pid=f'EVT-{eid:08d}'; db.execute('UPDATE events SET public_id=? WHERE id=?',(pid,eid)); return eid,pid
    def matchable_events(self,canonical_type):
        with self.connect() as db:return db.execute("SELECT * FROM events WHERE status IN ('ACTIVE','ENDED') AND canonical_type=? ORDER BY last_seen_at DESC",(canonical_type,)).fetchall()
    def get_source_link(self,source,source_event_id):
        with self.connect() as db:return db.execute('SELECT event_id FROM source_links WHERE source=? AND source_event_id=?',(source,source_event_id)).fetchone()
    def link_source_event(self,source,source_event_id,event_id):
        if not source_event_id:return
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO source_links(source,source_event_id,event_id) VALUES(?,?,?)',(source,source_event_id,event_id))
    def insert_alert(self,alert,content_hash,event_id,now):
        with self.connect() as db:db.execute('''INSERT INTO alerts(source,source_id,content_hash,event_id,event_type,headline,severity,urgency,certainty,status,sent_at,expires_at,area_desc,geometry_json,raw_json,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(alert.source,alert.source_id,content_hash,event_id,alert.event_type,alert.headline,alert.severity,alert.urgency,alert.certainty,alert.status,alert.sent_at,alert.expires_at,alert.area_desc,json.dumps(alert.geometry),json.dumps(alert.raw,sort_keys=True),now))
    def touch_event(self,event_id,severity,area_desc,now):
        with self.connect() as db:db.execute("UPDATE events SET severity=?,area_desc=?,last_seen_at=?,status=CASE WHEN status='ENDED' THEN 'ACTIVE' ELSE status END,ended_at=CASE WHEN status='ENDED' THEN NULL ELSE ended_at END WHERE id=?",(severity,area_desc,now,event_id))
    def get_event(self,event_id):
        with self.connect() as db:return db.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
    def latest_geometry(self,event_id):
        with self.connect() as db:
            r=db.execute('SELECT geometry_json FROM alerts WHERE event_id=? AND geometry_json IS NOT NULL ORDER BY id DESC LIMIT 1',(event_id,)).fetchone()
            return json.loads(r['geometry_json']) if r and r['geometry_json'] else None
    def queue_review(self,alert,event_id,confidence,reason,now):
        with self.connect() as db:db.execute('INSERT INTO review_queue(source,source_id,candidate_event_id,confidence,reason,created_at) VALUES(?,?,?,?,?,?)',(alert.source,alert.source_id,event_id,confidence,reason,now))
    def events_for_lifecycle(self):
        with self.connect() as db:return db.execute("SELECT * FROM events WHERE status IN ('ACTIVE','ENDED') ORDER BY last_seen_at").fetchall()
    def latest_alert(self,event_id):
        with self.connect() as db:return db.execute('SELECT * FROM alerts WHERE event_id=? ORDER BY id DESC LIMIT 1',(event_id,)).fetchone()
    def mark_ended(self,event_id,ended_at):
        with self.connect() as db:db.execute("UPDATE events SET status='ENDED',ended_at=?,notified_end=1 WHERE id=?",(ended_at,event_id))
    def mark_complete(self,event_id,when):
        with self.connect() as db:db.execute("UPDATE events SET status='COMPLETE',collection_complete_at=?,notified_complete=1 WHERE id=?",(when,event_id))
