import httpx
from ..models import NormalizedAlert
URL='https://eonet.gsfc.nasa.gov/api/v3/events'

async def fetch(client: httpx.AsyncClient, days=30):
    r=await client.get(URL, params={'status':'open','days':days})
    r.raise_for_status()
    return [normalize(x) for x in r.json().get('events',[])]

def normalize(event):
    cats=event.get('categories') or []
    category=(cats[0].get('id') if cats and isinstance(cats[0],dict) else 'Unknown')
    geometry=event.get('geometry') or []
    last=geometry[-1] if geometry else {}
    coords=last.get('coordinates')
    area=f'coordinates={coords}' if coords else ''
    return NormalizedAlert(source='NASA_EONET', source_id=str(event.get('id') or ''), event_type=category,
        headline=event.get('title') or category, severity='Unknown', urgency='Unknown', certainty='Observed',
        status='Ended' if event.get('closed') else 'Active', sent_at=last.get('date'), expires_at=event.get('closed'),
        area_desc=area, geometry=last if last else None, raw=event, source_event_id=str(event.get('id') or ''))
