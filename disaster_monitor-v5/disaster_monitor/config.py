from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    nws_poll_seconds: int = int(os.getenv('NWS_POLL_SECONDS', '60'))
    eonet_poll_seconds: int = int(os.getenv('EONET_POLL_SECONDS', '600'))
    request_timeout_seconds: float = float(os.getenv('REQUEST_TIMEOUT_SECONDS', '20'))
    database_path: str = os.getenv('DATABASE_PATH', 'data/disaster_monitor.db')
    outbox_path: str = os.getenv('OUTBOX_PATH', 'outbox')
    archive_path: str = os.getenv('ARCHIVE_PATH', 'archive')
    suppress_initial_sync: bool = os.getenv('SUPPRESS_INITIAL_SYNC', 'true').lower() in {'1','true','yes','on'}
    user_agent: str = os.getenv('NWS_USER_AGENT', 'DisasterMonitor/0.1 (set-contact-in-env)')
    eonet_days: int = int(os.getenv('EONET_DAYS', '30'))
    lifecycle_poll_seconds: int = int(os.getenv('LIFECYCLE_POLL_SECONDS', '60'))
    end_grace_minutes: int = int(os.getenv('END_GRACE_MINUTES', '30'))
    collection_grace_hours: int = int(os.getenv('COLLECTION_GRACE_HOURS', '24'))
    heartbeat_seconds: int = int(os.getenv('HEARTBEAT_SECONDS', '60'))
    health_path: str = os.getenv('HEALTH_PATH', 'data/health.json')
    log_path: str = os.getenv('LOG_PATH', 'logs/disaster_monitor.log')
    log_max_bytes: int = int(os.getenv('LOG_MAX_BYTES', str(5*1024*1024)))
    log_backup_count: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    backup_path: str = os.getenv('BACKUP_PATH', 'backups')
    backup_interval_hours: int = int(os.getenv('BACKUP_INTERVAL_HOURS', '24'))
    backup_keep_days: int = int(os.getenv('BACKUP_KEEP_DAYS', '14'))

settings = Settings()
