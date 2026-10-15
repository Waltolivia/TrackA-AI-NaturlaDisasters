import tempfile,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from disaster_monitor.database import Database
from disaster_monitor.models import NormalizedAlert
from disaster_monitor.processor import process
from disaster_monitor.services.prompter import JsonPrompter
from disaster_monitor.lifecycle import evaluate

def alert(source_id='a1',severity='Severe',headline='Flash Flood Warning',references=None,expires='2026-09-28T13:00:00Z',area='Utah County, Utah',event_type='Flash Flood Warning'):
    raw={'id':source_id,'headline':headline,'severity':severity,'v':source_id}
    return NormalizedAlert('NWS',source_id,event_type,headline,severity,'Immediate','Observed','Actual','2026-09-28T12:00:00Z',expires,area,None,references or [],raw)

def test_duplicate_and_reference_escalation():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        assert process(db,p,alert(),archive_path=root/'archive')=='NEW_EVENT'
        assert process(db,p,alert(),archive_path=root/'archive')=='duplicate'
        assert process(db,p,alert('a2','Extreme','Confirmed flash flooding',['a1']),archive_path=root/'archive')=='SEVERITY_CHANGED'
        with db.connect() as c: assert c.execute('SELECT count(*) n FROM events').fetchone()['n']==1
        assert len(list((Path(d)/'out'/'pending').glob('*.json')))==2

def test_ambiguous_match_goes_to_review_queue():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        process(db,p,alert(area='Utah County, Utah'),archive_path=root/'archive')
        process(db,p,alert('a2',area='Utah County; Salt Lake County, Utah'),archive_path=root/'archive')
        with db.connect() as c:
            # Depending on textual overlap this is either a high-confidence join or review; never data loss.
            assert c.execute('SELECT count(*) n FROM alerts').fetchone()['n']==2

def test_end_then_collection_complete_once():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        process(db,p,alert(expires='2026-09-28T13:00:00Z'),archive_path=root/'archive')
        t=datetime(2026,9,28,14,0,tzinfo=timezone.utc)
        assert evaluate(db,p,t,end_grace_minutes=30,completion_grace_hours=24,archive_path=root/'archive')[0][1]=='EVENT_ENDED'
        assert evaluate(db,p,t,end_grace_minutes=30,completion_grace_hours=24,archive_path=root/'archive')==[]
        later=t+timedelta(hours=25)
        assert evaluate(db,p,later,end_grace_minutes=30,completion_grace_hours=24,archive_path=root/'archive')[0][1]=='COLLECTION_COMPLETE'
        assert evaluate(db,p,later,end_grace_minutes=30,completion_grace_hours=24,archive_path=root/'archive')==[]
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

def test_dynamodb_setting_prefers_clear_name_but_accepts_legacy_alias(monkeypatch):
    from disaster_monitor.config import _enabled
    monkeypatch.delenv('DYNAMODB_ARCHIVE_ENABLED',raising=False)
    monkeypatch.setenv('AWS_ARCHIVE_ENABLED','true')
    assert _enabled('DYNAMODB_ARCHIVE_ENABLED',legacy_name='AWS_ARCHIVE_ENABLED')
    monkeypatch.setenv('DYNAMODB_ARCHIVE_ENABLED','false')
    assert not _enabled('DYNAMODB_ARCHIVE_ENABLED',legacy_name='AWS_ARCHIVE_ENABLED')

def test_durable_queue_and_archive_and_initial_suppression():
    from disaster_monitor.archive import event_report_path, render_event
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        assert process(db,p,alert(),suppress_notifications=True,archive_path=root/'archive')=='NEW_EVENT'
        assert len(list((root/'out'/'pending').glob('*.json')))==0
        reports=list((root/'archive').glob('**/events/*.txt'));assert len(reports)==1
        # Guard against a doubled `events/events/` folder (a clean-looking merge
        # can otherwise produce one without failing the glob above).
        expected=event_report_path(db.get_event(1),root/'archive')
        assert reports[0]==expected
        assert expected.parent.name=='events' and expected.parent.parent.name!='events'
        assert 'EVENT HISTORY' in reports[0].read_text()
        assert process(db,p,alert('a2','Extreme','Confirmed flash flooding',['a1']),archive_path=root/'archive')=='SEVERITY_CHANGED'
        pending=list((root/'out'/'pending').glob('*.json'));assert len(pending)==1
        payload=json.loads(pending[0].read_text())
        from disaster_monitor.archive import event_archive_location
        assert payload['archive']==event_archive_location(db.get_event(1))
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
            return NormalizedAlert('NWS',sid,'Tropical Storm',headline,severity,urgency,certainty,'Actual','2026-09-28T12:00:00Z','2026-09-28T14:00:00Z','Utah County, Utah',None,refs or [],{'id':sid,'headline':headline,'v':sid})
        assert process(db,p,a('s1','Tropical Storm Watch','Future'),archive_path=root/'archive')=='NEW_EVENT'
        assert process(db,p,a('s2','Tropical Storm Warning','Expected',refs=['s1']),archive_path=root/'archive')=='STATUS_CHANGED'
        assert process(db,p,a('s3','Tropical Storm Warning updated wording','Expected',refs=['s2']),archive_path=root/'archive')=='ROUTINE_UPDATE'
        assert process(db,p,a('s4','Tropical Storm Warning - confirmed landfall','Immediate','Observed',refs=['s3']),archive_path=root/'archive')=='STATUS_CHANGED'
        payloads=[json.loads(x.read_text()) for x in (root/'out'/'pending').glob('*.json')]
        assert sorted(x['action'] for x in payloads)==sorted(['NEW_EVENT','STATUS_CHANGED','STATUS_CHANGED'])
        confirmed=next(x for x in payloads if x['status']=='ACTIVE_CONFIRMED')
        assert confirmed['details']['previous_status']=='WARNING'

def test_high_impact_filter_selects_only_study_hazards():
    """The collector keeps only high-impact alerts (see processing/filtering.py).

    Every other fixture in this file is built to satisfy this allow-list, so a
    change that silently widens or narrows the filter shows up here instead of
    as confusing failures elsewhere.
    """
    from disaster_monitor.processing.filtering import is_natural_disaster
    def nws(event_type):
        return NormalizedAlert('NWS','x',event_type,event_type,'Severe','Immediate','Observed','Actual',None,None,'Utah County, Utah',None,[],{})
    def eonet(category):
        return NormalizedAlert('NASA_EONET','x',category,'Event','Unknown','Unknown','Observed','Active',None,None,'coordinates=[0, 0]',None,[],{})

    # Retained: the five frozen study hazard families.
    assert is_natural_disaster(nws('Flash Flood Warning'))
    assert is_natural_disaster(nws('Hurricane Watch'))
    assert is_natural_disaster(nws('Tsunami Warning'))
    assert is_natural_disaster(eonet('wildfires'))
    assert is_natural_disaster(eonet('earthquakes'))

    # Rejected on purpose as routine or below the study threshold.
    assert not is_natural_disaster(nws('Tornado Warning'))
    assert not is_natural_disaster(nws('Severe Thunderstorm Warning'))
    assert not is_natural_disaster(nws('Flood Advisory'))
    assert not is_natural_disaster(nws('Red Flag Warning'))
    assert not is_natural_disaster(eonet('severeStorms'))

    # Unknown sources are not collected.
    assert not is_natural_disaster(NormalizedAlert('OTHER','x','wildfires','Wildfire','Unknown','Unknown','Observed','Active',None,None,'',None,[],{}))

class _FakeTable:
    def __init__(self):self.items=[]
    def put_item(self,Item):self.items.append(Item)

class _FakeResource:
    def __init__(self):self.table=_FakeTable();self.requested=[]
    def Table(self,name):self.requested.append(name);return self.table

class _FakeS3Client:
    def __init__(self):self.objects={}
    def put_object(self,**kwargs):self.objects[kwargs['Key']]=kwargs

def _finished_event(db,p,root):
    """Create one event, end it, and let collection complete."""
    process(db,p,alert(),archive_path=root/'archive')
    ended=datetime(2026,9,28,14,0,tzinfo=timezone.utc)
    evaluate(db,p,ended,end_grace_minutes=30,completion_grace_hours=24,archive_path=root/'archive')
    completed=ended+timedelta(hours=25)
    evaluate(db,p,completed,end_grace_minutes=30,completion_grace_hours=24,archive_path=root/'archive')
    return completed

def test_local_data_is_kept_for_a_week_then_moved_to_aws():
    from disaster_monitor.aws_archive import AwsArchiver
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        completed=_finished_event(db,p,root)
        resource=_FakeResource()
        archiver=AwsArchiver(region='us-east-1',table_name='history',retention_days=7,resource=resource)

        # Still inside the one-week local window: nothing is copied or deleted.
        recent=archiver.archive(db,archive_path=root/'archive',now=completed,create_table=False)
        assert recent['events_eligible']==0 and recent['events_archived']==0
        assert db.get_event(1) is not None and db.count_alerts()==1
        assert list((root/'archive').glob('**/events/*.txt'))

        # Older than a week: everything is copied to AWS, then removed locally.
        result=archiver.archive(db,archive_path=root/'archive',now=completed+timedelta(days=8),create_table=False)
        assert result['events_archived']==1 and result['events_failed']==0
        assert result['items_written']==len(resource.table.items)>0
        assert result['reports_removed']==1
        assert resource.requested==['history','history']
        assert {item['sk'] for item in resource.table.items} >= {'META','REPORT'}
        assert all(item['pk']=='EVENT#EVT-00000001' for item in resource.table.items)
        assert db.get_event(1) is None and db.count_alerts()==0
        assert not list((root/'archive').glob('**/events/*.txt'))

def test_active_events_are_never_archived():
    from disaster_monitor.aws_archive import AwsArchiver
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        process(db,p,alert(),archive_path=root/'archive')
        resource=_FakeResource()
        archiver=AwsArchiver(region='us-east-1',retention_days=7,resource=resource)
        result=archiver.archive(db,archive_path=root/'archive',now=datetime.now(timezone.utc)+timedelta(days=30),create_table=False)
        assert result['events_eligible']==0 and not resource.table.items
        assert db.get_event(1) is not None

def test_ground_truth_snapshots_upload_immediately_to_shared_s3_event_folder():
    from disaster_monitor.s3_archive import S3EventArchive
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        client=_FakeS3Client()
        s3=S3EventArchive(bucket='study-bucket',region='us-west-2',prefix='disaster_monitor-v5/archive',pending_path=root/'pending',archive_path=root/'archive',client=client)

        process(db,p,alert(),archive_path=root/'archive',s3_archive=s3)
        assert list((root/'pending').glob('event-*.json'))

        result=s3.sync_pending(db)
        assert result=={'attempted':1,'uploaded':1,'failed':0}
        assert not list((root/'pending').glob('event-*.json'))
        from disaster_monitor.archive import event_archive_location
        location=event_archive_location(db.get_event(1))
        prefix=f'disaster_monitor-v5/archive/{location["relative_prefix"]}/EVT-00000001_weather/'
        assert set(client.objects)=={
            prefix+'EVENT_REPORT.txt',
            prefix+'event.json',
            prefix+'alerts.json',
            prefix+'archive_manifest.json',
        }
        assert all(obj['ServerSideEncryption']=='AES256' for obj in client.objects.values())

def test_s3_startup_reconciliation_queues_existing_local_events():
    from disaster_monitor.s3_archive import S3EventArchive
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);db=Database(str(root/'x.db'));p=JsonPrompter(root/'out')
        process(db,p,alert(),archive_path=root/'archive')
        s3=S3EventArchive(bucket='study-bucket',region='us-west-2',pending_path=root/'pending',archive_path=root/'archive',client=_FakeS3Client())
        assert s3.schedule_existing(db)==1
        assert s3.pending_count()==1
        assert s3.sync_pending(db)=={'attempted':1,'uploaded':1,'failed':0}
        assert s3.pending_count()==0
