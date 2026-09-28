import json, shutil
from datetime import datetime, timezone
from pathlib import Path

class HealthTracker:
    def __init__(self,path,database_path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.database_path=Path(database_path); self.started_at=self.now(); self.sources={}
    @staticmethod
    def now(): return datetime.now(timezone.utc).isoformat()
    def source_ok(self,name,received): self.sources[name]={'status':'OK','last_success':self.now(),'received':received,'last_error':None}
    def source_error(self,name,error):
        old=self.sources.get(name,{})
        self.sources[name]={'status':'ERROR','last_success':old.get('last_success'),'received':old.get('received',0),'last_error':str(error),'last_error_at':self.now()}
    def write(self):
        disk=shutil.disk_usage(self.database_path.parent if self.database_path.parent.exists() else '.')
        payload={'status':'RUNNING','started_at':self.started_at,'heartbeat_at':self.now(),'sources':self.sources,'database':str(self.database_path),'disk_free_bytes':disk.free}
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(payload,indent=2)); tmp.replace(self.path)
