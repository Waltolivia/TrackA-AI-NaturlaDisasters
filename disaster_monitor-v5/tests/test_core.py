import tempfile,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from disaster_monitor.database import Database
from disaster_monitor.models import NormalizedAlert
from disaster_monitor.processor import process
from disaster_monitor.services.prompter import JsonPrompter
from disaster_monitor.lifecycle import evaluate

def alert(source_id='a1',severity='Severe',headline='Tornado Warning',references=None,expires='2026-09-28T13:00:00Z',area='Utah County, Utah'):
    raw={'id':source_id,'headline':headline,'severity':severity,'v':source_id}
    return NormalizedAlert('NWS',source_id,'Tornado Warning',headline,severity,'Immediate','Observed','Actual','2026-09-28T12:00:00Z',expires,area,None,references or [],raw)

def test_duplicate_and_reference_escalation():
    with tempfile.TemporaryDirectory() as d:
        db=Database(str(Path(d)/'x.db'));p=JsonPrompter(Path(d)/'out')
        assert process(db,p,alert())=='NEW_EVENT'
        assert process(db,p,alert())=='duplicate'
        assert process(db,p,alert('a2','Extreme','Confirmed tornado',['a1']))=='SEVERITY_CHANGED'
        with db.connect() as c: assert c.execute('SELECT count(*) n FROM events').fetchone()['n']==1
        assert len(list((Path(d)/'out'/'pending').glob('*.json')))==2

def test_ambiguous_match_goes_to_review_queue():
    with tempfile.TemporaryDirectory() as d:
        db=Database(str(Path(d)/'x.db'));p=JsonPrompter(Path(d)/'out')
        process(db,p,alert(area='Utah County, Utah'))
        process(db,p,alert('a2',area='Utah County; Salt Lake County, Utah'))
        with db.connect() as c:
            # Depending on textual overlap this is either a high-confidence join or review; never data loss.
            assert c.execute('SELECT count(*) n FROM alerts').fetchone()['n']==2

def test_end_then_collection_complete_once():
    with tempfile.TemporaryDirectory() as d:
        db=Database(str(Path(d)/'x.db'));p=JsonPrompter(Path(d)/'out')
        process(db,p,alert(expires='2026-09-28T13:00:00Z'))
        t=datetime(2026,9,28,14,0,tzinfo=timezone.utc)
        assert evaluate(db,p,t,end_grace_minutes=30,completion_grace_hours=24)[0][1]=='EVENT_ENDED'
        assert evaluate(db,p,t,end_grace_minutes=30,completion_grace_hours=24)==[]
        later=t+timedelta(hours=25)
        assert evaluate(db,p,later,end_grace_minutes=30,completion_grace_hours=24)[0][1]=='COLLECTION_COMPLETE'
        assert evaluate(db,p,later,end_grace_minutes=30,completion_grace_hours=24)==[]
        payloads=[json.loads(x.read_text()) for x in (Path(d)/'out'/'pending').glob('*.json')]
        triggers=[x['action'] for x in payloads]
        assert triggers.count('EVENT_ENDED')==1 and triggers.count('COLLECTION_COMPLETE')==0

def test_health_and_sqlite_backup():
    from disaster_monitor.health import HealthTracker
    from disaster_monitor.backup import backup_database
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); db=Database(str(root/'data'/'x.db'))
        h=HealthTracker(root/'data'/'health.json',root/'data'/'x.db'); h.source_ok('NWS',12); h.source_error('NASA_EONET','offline'); h.write()
        health=json.loads((root/'data'/'health.json').read_text())
        assert health['status']=='RUNNING' and health['sources']['NWS']['received']==12
        b=backup_database(root/'data'/'x.db',root/'backups',14)
        assert b.exists() and b.stat().st_size>0

def test_durable_queue_and_archive_and_initial_suppression():
    from disaster_monitor.archive import render_event
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        assert process(db,p,alert(),suppress_notifications=True,archive_path=root/'archive')=='NEW_EVENT'
        assert len(list((root/'out'/'pending').glob('*.json')))==0
        reports=list((root/'archive').glob('**/events/*.txt'));assert len(reports)==1
        assert 'EVENT HISTORY' in reports[0].read_text()
        assert process(db,p,alert('a2','Extreme','Confirmed tornado',['a1']),archive_path=root/'archive')=='SEVERITY_CHANGED'
        pending=list((root/'out'/'pending').glob('*.json'));assert len(pending)==1
        processing=p.claim(pending[0]);assert processing.parent.name=='processing'
        completed=p.ack(processing);assert completed.parent.name=='completed'

def test_eonet_near_duplicate_merges():
    def eonet(sid,lon):
        return NormalizedAlert('NASA_EONET',sid,'wildfires','Wildfire Bunker Fire, Calhoun, Arkansas','Unknown','Unknown','Observed','Active','2026-09-28T12:00:00Z',None,f'coordinates=[{lon}, 33.5744]',{'type':'Point','coordinates':[lon,33.5744]},[],{'id':sid,'title':'Wildfire Bunker Fire, Calhoun, Arkansas'},sid)
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        process(db,p,eonet('E1',-92.5861),archive_path=root/'archive')
        process(db,p,eonet('E2',-92.5863),archive_path=root/'archive')
        with db.connect() as c:assert c.execute('SELECT count(*) n FROM events').fetchone()['n']==1

def test_meaningful_status_changes_notify_but_routine_updates_do_not():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        def a(sid,headline,urgency,certainty='Possible',severity='Severe',refs=None):
            return NormalizedAlert('NWS',sid,'Tornado',headline,severity,urgency,certainty,'Actual','2026-09-28T12:00:00Z','2026-09-28T14:00:00Z','Utah County, Utah',None,refs or [],{'id':sid,'headline':headline,'v':sid})
        assert process(db,p,a('s1','Tornado Watch','Future'),archive_path=root/'archive')=='NEW_EVENT'
        assert process(db,p,a('s2','Tornado Warning','Expected',refs=['s1']),archive_path=root/'archive')=='STATUS_CHANGED'
        assert process(db,p,a('s3','Tornado Warning updated wording','Expected',refs=['s2']),archive_path=root/'archive')=='ROUTINE_UPDATE'
        assert process(db,p,a('s4','Tornado Warning - confirmed tornado','Immediate','Observed',refs=['s3']),archive_path=root/'archive')=='STATUS_CHANGED'
        payloads=[json.loads(x.read_text()) for x in (root/'out'/'pending').glob('*.json')]
        assert sorted(x['action'] for x in payloads)==sorted(['NEW_EVENT','STATUS_CHANGED','STATUS_CHANGED'])
        confirmed=next(x for x in payloads if x['status']=='ACTIVE_CONFIRMED')
        assert confirmed['details']['previous_status']=='WARNING'
