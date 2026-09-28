import asyncio,logging,random
import httpx
from .config import settings
from .database import Database
from .services.prompter import JsonPrompter
from .processor import process
from .collectors import nws,eonet
from .lifecycle import evaluate

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('disaster-monitor')

async def worker(name, interval, getter, db, prompter, client):
    failures=0
    while True:
        try:
            alerts=await getter(client)
            counts={}
            for alert in alerts:
                result=process(db,prompter,alert); counts[result]=counts.get(result,0)+1
            log.info('%s poll OK received=%d results=%s',name,len(alerts),counts)
            failures=0; delay=interval
        except asyncio.CancelledError: raise
        except Exception as exc:
            failures+=1
            delay=min(interval*(2**min(failures,5)),1800)
            delay*=random.uniform(.85,1.15)
            log.exception('%s poll failed; retry in %.0fs: %s',name,delay,exc)
        await asyncio.sleep(delay)

async def lifecycle_worker(db,prompter):
    while True:
        try:
            changes=evaluate(db,prompter,completion_grace_hours=settings.collection_grace_hours,end_grace_minutes=settings.end_grace_minutes)
            if changes: log.info('lifecycle changes=%s',changes)
        except asyncio.CancelledError: raise
        except Exception: log.exception('lifecycle evaluation failed')
        await asyncio.sleep(settings.lifecycle_poll_seconds)

async def main():
    db=Database(settings.database_path); prompter=JsonPrompter(settings.outbox_path)
    timeout=httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout,follow_redirects=True) as client:
        await asyncio.gather(
            worker('NWS',settings.nws_poll_seconds,lambda c:nws.fetch(c,settings.user_agent),db,prompter,client),
            worker('NASA_EONET',settings.eonet_poll_seconds,lambda c:eonet.fetch(c,settings.eonet_days),db,prompter,client),
            lifecycle_worker(db,prompter))

if __name__=='__main__': asyncio.run(main())
