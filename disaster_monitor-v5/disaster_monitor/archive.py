import json,re,textwrap
from pathlib import Path
from datetime import datetime

def _dt(v):
    if not v:return None
    try:return datetime.fromisoformat(v.replace('Z','+00:00'))
    except Exception:return None

def _safe(s):return re.sub(r'[^A-Za-z0-9._-]+','-',str(s or 'event')).strip('-')[:80] or 'event'
def _wrap(text,width=112):
    if not text:return 'N/A'
    return '\n'.join(textwrap.fill(p,width=width,replace_whitespace=False) if p.strip() else '' for p in str(text).splitlines())
def _raw(alert):
    try:return json.loads(alert['raw_json'])
    except Exception:return {}
def _nws_fields(raw):
    p=raw.get('properties') or {}
    params=p.get('parameters') or {}
    def val(*names):
        for n in names:
            x=p.get(n)
            if x:return x
        return None
    return {'description':val('description'),'instruction':val('instruction'),'area':val('areaDesc'),
      'sender':val('senderName','sender'),'parameters':params}

def render_event(db,event_id,root='archive'):
    event=db.get_event(event_id);alerts=db.alerts_for_event(event_id)
    opened=_dt(event['opened_at']);year=f'{opened.year:04d}' if opened else 'unknown';month=f'{opened.month:02d}' if opened else 'unknown'
    folder=Path(root)/year/month/'events';folder.mkdir(parents=True,exist_ok=True)
    name=_safe(event['title'] if event['title'] else event['canonical_type'])
    path=folder/f'{event["public_id"]}_{name}.txt'
    lines=['='*120,'DISASTER EVENT REPORT','='*120,'',
      f'Event: {event["public_id"]}    Type: {event["canonical_type"]}    Phase: {event["operational_phase"]}    Lifecycle: {event["status"]}    Highest Severity: {event["severity"] or "Unknown"}',
      f'Started: {event["opened_at"]}    Last Seen: {event["last_seen_at"]}    Ended: {event["ended_at"] or "N/A"}',
      f'Primary Location: {event["area_desc"] or "N/A"}','', 'EVENT HISTORY','='*120]
    for i,a in enumerate(alerts,1):
        raw=_raw(a);nf=_nws_fields(raw) if a['source']=='NWS' else {}
        lines += ['',f'[{i:02d}] {a["sent_at"] or a["observed_at"]}    {a["source"]}    {a["event_type"]}    {a["severity"] or "Unknown"}','-'*120,
          f'Headline: {a["headline"] or "N/A"}',f'Expires: {a["expires_at"] or "N/A"}    Urgency: {a["urgency"] or "N/A"}    Certainty: {a["certainty"] or "N/A"}',
          '', 'AFFECTED AREAS','-'*120,_wrap(nf.get('area') or a['area_desc'])]
        if nf.get('description'):lines += ['','DESCRIPTION','-'*120,_wrap(nf['description'])]
        if nf.get('instruction'):lines += ['','INSTRUCTIONS','-'*120,_wrap(nf['instruction'])]
        if nf.get('parameters'):lines += ['','ADDITIONAL NWS PARAMETERS','-'*120,_wrap(json.dumps(nf['parameters'],indent=2,ensure_ascii=False))]
        lines += ['','SOURCE','-'*120,f'Source: {a["source"]}    Source Alert ID: {a["source_id"]}']
    lines += ['','='*120,'SOURCE SUMMARY','='*120]
    counts={}
    for a in alerts:counts[a['source']]=counts.get(a['source'],0)+1
    lines.append('    '.join(f'{k}: {v}' for k,v in sorted(counts.items())) or 'No source records')
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8');render_month_index(db,opened,root);return path

def render_month_index(db,when,root='archive'):
    if not when:return None
    events=db.events_opened_in_month(when.year,when.month);folder=Path(root)/f'{when.year:04d}'/f'{when.month:02d}';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{when.strftime("%B_%Y")}_Events.txt';lines=['='*120,f'{when.strftime("%B %Y").upper()} - DISASTER EVENT INDEX','='*120,'',
      f'{"EVENT ID":<14} {"STARTED":<20} {"TYPE":<20} {"SEVERITY":<10} {"STATUS":<10} LOCATION / NAME','-'*120]
    totals={}
    for e in events:
        d=_dt(e['opened_at']);started=d.strftime('%Y-%m-%d %H:%M') if d else e['opened_at'][:19];loc=(e['area_desc'] or e['title'] or '')
        lines.append(f'{e["public_id"]:<14} {started:<20} {e["canonical_type"][:20]:<20} {(e["severity"] or "Unknown")[:10]:<10} {e["status"]:<10} {loc}')
        totals[e['canonical_type']]=totals.get(e['canonical_type'],0)+1
    lines += ['','-'*120,f'Total events: {len(events)}','    '.join(f'{k}: {v}' for k,v in sorted(totals.items()))]
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8');return path
