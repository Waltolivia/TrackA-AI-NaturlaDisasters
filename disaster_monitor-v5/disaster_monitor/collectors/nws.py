import httpx
from ..models import NormalizedAlert

URL='https://api.weather.gov/alerts/active'

async def fetch(client: httpx.AsyncClient, user_agent: str):
    r=await client.get(URL, headers={'User-Agent':user_agent,'Accept':'application/geo+json'})
    r.raise_for_status()
    return [normalize(x) for x in r.json().get('features',[])]

def normalize(feature):
    p=feature.get('properties') or {}
    refs=[]
    for ref in p.get('references') or []:
        if isinstance(ref,dict) and ref.get('identifier'): refs.append(ref['identifier'])
    return NormalizedAlert(
        source='NWS', source_id=str(p.get('id') or feature.get('id') or ''),
        event_type=p.get('event') or 'Unknown', headline=p.get('headline') or p.get('event') or 'NWS alert',
        severity=p.get('severity') or 'Unknown', urgency=p.get('urgency') or 'Unknown', certainty=p.get('certainty') or 'Unknown',
        status=p.get('status') or 'Actual', sent_at=p.get('sent'), expires_at=p.get('expires'), area_desc=p.get('areaDesc') or '',
        geometry=feature.get('geometry'), references=refs, raw=feature)
