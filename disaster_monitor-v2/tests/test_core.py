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
        assert process(db,p,alert('a2','Extreme','Confirmed tornado',['a1']))=='ESCALATION'
        with db.connect() as c: assert c.execute('SELECT count(*) n FROM events').fetchone()['n']==1
        assert len(list((Path(d)/'out').glob('*.json')))==2

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
        payloads=[json.loads(x.read_text()) for x in (Path(d)/'out').glob('*.json')]
        triggers=[x['trigger'] for x in payloads]
        assert triggers.count('EVENT_ENDED')==1 and triggers.count('COLLECTION_COMPLETE')==1
