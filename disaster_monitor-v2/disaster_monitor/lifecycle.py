from datetime import datetime,timezone,timedelta

def _dt(value):
    if not value:return None
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def _explicitly_ended(alert):
    if not alert:return False
    status=(alert['status'] or '').lower()
    return status in {'ended','cancel','cancelled','expired'}

def evaluate(db,prompter,now=None,end_grace_minutes=30,completion_grace_hours=24):
    now=now or datetime.now(timezone.utc); results=[]
    for event in db.events_for_lifecycle():
        latest=db.latest_alert(event['id'])
        if event['status']=='ACTIVE':
            expiry=_dt(latest['expires_at']) if latest else None
            stale_expiry=expiry and now>=expiry+timedelta(minutes=end_grace_minutes)
            if _explicitly_ended(latest) or stale_expiry:
                when=now.isoformat(); db.mark_ended(event['id'],when); refreshed=db.get_event(event['id'])
                prompter.emit(refreshed,latest,'EVENT_ENDED',{'ended_reason':'explicit_status' if _explicitly_ended(latest) else 'expiration_grace_elapsed'})
                results.append((event['public_id'],'EVENT_ENDED'))
        elif event['status']=='ENDED':
            ended=_dt(event['ended_at'])
            if ended and now>=ended+timedelta(hours=completion_grace_hours):
                when=now.isoformat(); db.mark_complete(event['id'],when); refreshed=db.get_event(event['id'])
                prompter.emit(refreshed,latest,'COLLECTION_COMPLETE',{'collection_grace_hours':completion_grace_hours})
                results.append((event['public_id'],'COLLECTION_COMPLETE'))
    return results
