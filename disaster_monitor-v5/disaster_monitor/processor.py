import hashlib,json
from datetime import datetime,timezone
from .processing.filtering import is_natural_disaster
from .processing.matcher import match_existing,canonical_type
from .processing.severity import escalated
from .processing.status import phase
from .archive import render_event

def digest(alert):return hashlib.sha256(json.dumps(alert.raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def process(db,prompter,alert,high_threshold=.78,review_threshold=.58,suppress_notifications=False,archive_path='archive'):
    if not is_natural_disaster(alert):return 'filtered'
    h=digest(alert)
    if db.seen(alert.source,alert.source_id,h):return 'duplicate'
    now=datetime.now(timezone.utc).isoformat();event_id,confidence,reason=match_existing(db,alert);created=False
    if event_id is None or confidence<review_threshold:
        event_id,_=db.create_event(canonical_type(alert.event_type),alert.headline,alert.severity,alert.area_desc,now);created=True
    elif confidence<high_threshold:
        candidate=event_id;event_id,_=db.create_event(canonical_type(alert.event_type),alert.headline,alert.severity,alert.area_desc,now);created=True
        db.queue_review(alert,candidate,confidence,reason,now)
    before=db.get_event(event_id);new_phase=phase(alert)
    db.insert_alert(alert,h,event_id,now);db.link_source_event(alert.source,alert.source_event_id,event_id)
    db.touch_event(event_id,alert.severity,alert.area_desc or before['area_desc'],now,new_phase);after=db.get_event(event_id)
    severity_changed=not created and escalated(before['severity'],alert.severity)
    phase_changed=not created and before['operational_phase'] != new_phase
    if created: trigger='NEW_EVENT'
    elif phase_changed: trigger='STATUS_CHANGED'
    elif severity_changed: trigger='SEVERITY_CHANGED'
    else: trigger='ROUTINE_UPDATE'
    # Only meaningful live changes are downstream jobs. Routine revisions remain in DB/archive.
    if trigger != 'ROUTINE_UPDATE':
        prompter.emit(after,alert,trigger,{'match_confidence':confidence,'match_reason':reason,'previous_status':None if created else before['operational_phase'],'status':new_phase,'previous_severity':None if created else before['severity'],'severity':alert.severity},suppress=suppress_notifications)
    render_event(db,event_id,archive_path)
    return trigger
