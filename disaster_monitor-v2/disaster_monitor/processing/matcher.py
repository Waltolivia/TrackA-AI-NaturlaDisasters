import json, math, re
from datetime import datetime, timezone
from difflib import SequenceMatcher

ALIASES={'severe storms':'severe storm','wildfires':'wildfire','volcanoes':'volcano','earthquakes':'earthquake','floods':'flood'}

def canonical_type(value):
    x=(value or 'unknown').lower().strip()
    x=re.sub(r'\b(warning|watch|advisory|statement|emergency|update)\b','',x)
    x=' '.join(x.split())
    return ALIASES.get(x,x)

def area_similarity(a,b):
    if not a or not b: return 0.0
    aset={x.strip().lower() for x in re.split(r'[;,]',a) if x.strip()}
    bset={x.strip().lower() for x in re.split(r'[;,]',b) if x.strip()}
    if aset and bset:
        overlap=len(aset & bset)/max(1,min(len(aset),len(bset)))
        if overlap: return overlap
    return SequenceMatcher(None,a.lower(),b.lower()).ratio()

def _points(geometry):
    if not geometry: return []
    if geometry.get('type')=='Point': return [geometry.get('coordinates')]
    coords=geometry.get('coordinates') or []
    if geometry.get('type')=='Polygon': return coords[0] if coords else []
    if geometry.get('type')=='MultiPolygon': return [p for poly in coords for ring in poly for p in ring]
    return []

def _centroid(geometry):
    pts=[p for p in _points(geometry) if isinstance(p,list) and len(p)>=2]
    if not pts: return None
    return sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts)

def geo_similarity(a,b):
    ca,cb=_centroid(a),_centroid(b)
    if not ca or not cb: return None
    # Approximate great-circle distance. Enough for a matching feature, not geodesic analysis.
    lon1,lat1,lon2,lat2=map(math.radians,[ca[0],ca[1],cb[0],cb[1]])
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    km=6371*2*math.asin(min(1,math.sqrt(h)))
    if km<=25:return 1.0
    if km<=75:return .85
    if km<=200:return .65
    if km<=500:return .35
    return 0.0

def _parse_time(value):
    if not value:return None
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def time_similarity(alert,event):
    a=_parse_time(alert.sent_at) or datetime.now(timezone.utc)
    e=_parse_time(event['last_seen_at'])
    if not e:return .5
    hours=abs((a-e).total_seconds())/3600
    if hours<=6:return 1.0
    if hours<=24:return .85
    if hours<=72:return .6
    if hours<=168:return .35
    return .1

def match_existing(db, alert):
    # A CAP reference to an already stored alert is stronger than fuzzy matching.
    for ref in alert.references:
        row=db.find_alert_by_source_id(alert.source,ref)
        if row and row['event_id']:
            return row['event_id'],1.0,'reference'
    # Stable upstream event IDs (EONET etc.) can map directly to our event.
    if alert.source_event_id:
        link=db.get_source_link(alert.source,alert.source_event_id)
        if link:return link['event_id'],1.0,'source_event_id'
    ctype=canonical_type(alert.event_type)
    best=(None,0.0,'none')
    for event in db.matchable_events(ctype):
        area=area_similarity(alert.area_desc,event['area_desc'])
        geo=geo_similarity(alert.geometry,db.latest_geometry(event['id']))
        time=time_similarity(alert,event)
        # Geography is useful when present; area text remains important for NWS county/zone alerts.
        if geo is None: score=.68*area+.32*time
        else: score=.48*area+.32*geo+.20*time
        if score>best[1]:best=(event['id'],score,'fuzzy')
    return best
