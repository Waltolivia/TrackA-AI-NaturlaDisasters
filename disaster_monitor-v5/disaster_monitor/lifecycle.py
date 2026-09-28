from datetime import datetime,timezone,timedelta
from .archive import render_event

def _dt(value):
    if not value:return None
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def _explicitly_ended(alert):return bool(alert) and (alert['status'] or '').lower() in {'ended','cancel','cancelled','expired'}

def evaluate(db,prompter,now=None,end_grace_minutes=30,completion_grace_hours=24,archive_path='archive'):
    now=now or datetime.now(timezone.utc);results=[]
    for event in db.events_for_lifecycle():
        latest=db.latest_alert(event['id'])
        if event['status']=='ACTIVE':
            expiry=_dt(latest['expires_at']) if latest else None;stale=expiry and now>=expiry+timedelta(minutes=end_grace_minutes)
            if _explicitly_ended(latest) or stale:
                when=now.isoformat();db.mark_ended(event['id'],when);ref=db.get_event(event['id']);prompter.emit(ref,latest,'EVENT_ENDED',{'ended_reason':'explicit_status' if _explicitly_ended(latest) else 'expiration_grace_elapsed'});render_event(db,event['id'],archive_path);results.append((event['public_id'],'EVENT_ENDED'))
        elif event['status']=='ENDED':
            ended=_dt(event['ended_at'])
            if ended and now>=ended+timedelta(hours=completion_grace_hours):
                when=now.isoformat();db.mark_complete(event['id'],when);ref=db.get_event(event['id']);# Collection completion is archive/database-only by default; it is not a live downstream job.
                render_event(db,event['id'],archive_path);results.append((event['public_id'],'COLLECTION_COMPLETE'))
    return results
