import json, shutil, uuid
from pathlib import Path
from datetime import datetime,timezone

class JsonPrompter:
    """Durable filesystem queue. Consumers claim pending messages, then ack/fail them."""
    def __init__(self,path):
        self.root=Path(path)
        for name in ('pending','processing','completed','failed'):(self.root/name).mkdir(parents=True,exist_ok=True)
    def emit(self,event,alert,trigger,extra=None,suppress=False):
        if suppress:return None
        stamp=datetime.now(timezone.utc)
        def get(name,default=None):
            if alert is None:return default
            try:return alert[name]
            except (KeyError,TypeError):return getattr(alert,name,default)
        title=get('headline',event['title']) or event['title']
        payload={'schema_version':3,'message_id':f'MSG-{uuid.uuid4().hex}','action':trigger,'event_id':event['public_id'],
          'disaster':{'type':event['canonical_type'],'name':_event_name(event,title),'location':get('area_desc',event['area_desc'])},
          'severity':get('severity',event['severity']),'status':event['operational_phase'],'event_lifecycle':event['status'],'source':get('source'),
          'source_alert_id':get('source_id'),'sent_at':get('sent_at'),'generated_at':stamp.isoformat(),'headline':title}
        if extra:payload['details']=extra
        target=self.root/'pending'/f'{stamp.strftime("%Y%m%dT%H%M%S.%fZ")}_{event["public_id"]}_{trigger}_{payload["message_id"]}.json'
        tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(target);return target
    def claim(self,path):return _move(path,self.root/'processing')
    def ack(self,path):return _move(path,self.root/'completed')
    def fail(self,path):return _move(path,self.root/'failed')

def _move(path,dest):
    p=Path(path);dest.mkdir(parents=True,exist_ok=True);target=dest/p.name;shutil.move(str(p),str(target));return target

def _event_name(event,title):
    t=(title or '').strip();ctype=(event['canonical_type'] or '').lower()
    # Named storms/fires are useful names; generic NWS warning headlines are not.
    if any(k in t.lower() for k in ('hurricane ','tropical storm ','typhoon ','wildfire ','fire ')) and ' issued ' not in t.lower():return t
    return None
