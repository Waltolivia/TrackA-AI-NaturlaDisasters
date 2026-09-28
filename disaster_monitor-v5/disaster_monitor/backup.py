import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

def backup_database(database_path,backup_path,keep_days=14):
    source=Path(database_path); destdir=Path(backup_path); destdir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); dest=destdir/f'disaster_monitor_{stamp}.db'
    src=sqlite3.connect(source); dst=sqlite3.connect(dest)
    try: src.backup(dst)
    finally: dst.close(); src.close()
    cutoff=datetime.now(timezone.utc)-timedelta(days=keep_days)
    for old in destdir.glob('disaster_monitor_*.db'):
        if datetime.fromtimestamp(old.stat().st_mtime,timezone.utc)<cutoff: old.unlink(missing_ok=True)
    return dest
