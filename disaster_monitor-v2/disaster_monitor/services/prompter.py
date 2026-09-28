import json
from pathlib import Path
from datetime import datetime,timezone
class JsonPrompter:
    def __init__(self,path):self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
    def emit(self,event,alert,trigger,extra=None):
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        def get(name,default=None):
            if alert is None:return default
            try:return alert[name]
            except (KeyError,TypeError):return getattr(alert,name,default)
        payload={'schema_version':2,'trigger':trigger,'event_id':event['public_id'],'event_type':event['canonical_type'],'event_status':event['status'],'location':get('area_desc',event['area_desc']),'severity':get('severity',event['severity']),'urgency':get('urgency'),'certainty':get('certainty'),'headline':get('headline',event['title']),'source':get('source'),'source_alert_id':get('source_id'),'sent_at':get('sent_at'),'generated_at':datetime.now(timezone.utc).isoformat()}
        if extra:payload['details']=extra
        target=self.path/f'{stamp}_{event["public_id"]}_{trigger}.json';tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(payload,indent=2),encoding='utf-8');tmp.replace(target);return target
