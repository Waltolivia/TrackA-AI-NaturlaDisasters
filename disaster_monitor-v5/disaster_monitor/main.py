import asyncio,logging,random,signal
from logging.handlers import RotatingFileHandler
from pathlib import Path
import httpx
from .config import settings
from .database import Database
from .services.prompter import JsonPrompter
from .processor import process
from .collectors import nws,eonet
from .lifecycle import evaluate
from .health import HealthTracker
from .backup import backup_database

def configure_logging():
    Path(settings.log_path).parent.mkdir(parents=True,exist_ok=True)
    fmt=logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    root=logging.getLogger(); root.setLevel(logging.INFO); root.handlers.clear()
    console=logging.StreamHandler(); console.setFormatter(fmt); root.addHandler(console)
    rotating=RotatingFileHandler(settings.log_path,maxBytes=settings.log_max_bytes,backupCount=settings.log_backup_count); rotating.setFormatter(fmt); root.addHandler(rotating)
configure_logging(); log=logging.getLogger('disaster-monitor')

async def worker(name, interval, getter, db, prompter, client, health):
    failures=0; first_success=True
    while True:
        try:
            alerts=await getter(client); counts={}
            for alert in alerts:
                result=process(db,prompter,alert,suppress_notifications=(first_success and settings.suppress_initial_sync),archive_path=settings.archive_path); counts[result]=counts.get(result,0)+1
            health.source_ok(name,len(alerts)); log.info('%s poll OK received=%d results=%s initial_sync=%s',name,len(alerts),counts,first_success)
            first_success=False; failures=0; delay=interval
        except asyncio.CancelledError: raise
        except Exception as exc:
            health.source_error(name,exc); failures+=1; delay=min(interval*(2**min(failures,5)),1800)*random.uniform(.85,1.15)
            log.exception('%s poll failed; retry in %.0fs: %s',name,delay,exc)
        await asyncio.sleep(delay)

async def lifecycle_worker(db,prompter):
    while True:
        try:
            changes=evaluate(db,prompter,completion_grace_hours=settings.collection_grace_hours,end_grace_minutes=settings.end_grace_minutes,archive_path=settings.archive_path)
            if changes: log.info('lifecycle changes=%s',changes)
        except asyncio.CancelledError: raise
        except Exception: log.exception('lifecycle evaluation failed')
        await asyncio.sleep(settings.lifecycle_poll_seconds)

async def heartbeat_worker(health):
    while True:
        try: health.write()
        except asyncio.CancelledError: raise
        except Exception: log.exception('heartbeat write failed')
        await asyncio.sleep(settings.heartbeat_seconds)

async def backup_worker():
    while True:
        try:
            path=await asyncio.to_thread(backup_database,settings.database_path,settings.backup_path,settings.backup_keep_days); log.info('database backup created %s',path)
        except asyncio.CancelledError: raise
        except Exception: log.exception('database backup failed')
        await asyncio.sleep(settings.backup_interval_hours*3600)

async def main():
    db=Database(settings.database_path); prompter=JsonPrompter(settings.outbox_path); health=HealthTracker(settings.health_path,settings.database_path)
    timeout=httpx.Timeout(settings.request_timeout_seconds)
    stop=asyncio.Event(); loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try: loop.add_signal_handler(sig,stop.set)
        except NotImplementedError: pass
    async with httpx.AsyncClient(timeout=timeout,follow_redirects=True) as client:
        tasks=[asyncio.create_task(worker('NWS',settings.nws_poll_seconds,lambda c:nws.fetch(c,settings.user_agent),db,prompter,client,health)),asyncio.create_task(worker('NASA_EONET',settings.eonet_poll_seconds,lambda c:eonet.fetch(c,settings.eonet_days),db,prompter,client,health)),asyncio.create_task(lifecycle_worker(db,prompter)),asyncio.create_task(heartbeat_worker(health)),asyncio.create_task(backup_worker())]
        log.info('Disaster Monitor started')
        await stop.wait(); log.info('shutdown requested')
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        try: health.write()
        except Exception: pass
        log.info('Disaster Monitor stopped cleanly')
if __name__=='__main__': asyncio.run(main())
