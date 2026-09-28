import hashlib,json
from datetime import datetime,timezone
from .processing.filtering import is_natural_disaster
from .processing.matcher import match_existing,canonical_type
from .processing.severity import escalated

def digest(alert):return hashlib.sha256(json.dumps(alert.raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def process(db,prompter,alert,high_threshold=.78,review_threshold=.58):
    if not is_natural_disaster(alert):return 'filtered'
    h=digest(alert)
    if db.seen(alert.source,alert.source_id,h):return 'duplicate'
    now=datetime.now(timezone.utc).isoformat(); event_id,confidence,reason=match_existing(db,alert); created=False
    if event_id is None or confidence<review_threshold:
        event_id,_=db.create_event(canonical_type(alert.event_type),alert.headline,alert.severity,alert.area_desc,now); created=True
    elif confidence<high_threshold:
        # Preserve data, but do not silently merge an ambiguous update. It becomes its own event and is reviewable.
        candidate=event_id
        event_id,_=db.create_event(canonical_type(alert.event_type),alert.headline,alert.severity,alert.area_desc,now); created=True
        db.queue_review(alert,candidate,confidence,reason,now)
    before=db.get_event(event_id)
    db.insert_alert(alert,h,event_id,now); db.link_source_event(alert.source,alert.source_event_id,event_id)
    db.touch_event(event_id,alert.severity,alert.area_desc or before['area_desc'],now); after=db.get_event(event_id)
    trigger='NEW_EVENT' if created else ('ESCALATION' if escalated(before['severity'],alert.severity) else 'UPDATE')
    if trigger in {'NEW_EVENT','ESCALATION'}:prompter.emit(after,alert,trigger,{'match_confidence':confidence,'match_reason':reason})
    return trigger
