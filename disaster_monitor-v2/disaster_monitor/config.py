from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    nws_poll_seconds: int = int(os.getenv('NWS_POLL_SECONDS', '60'))
    eonet_poll_seconds: int = int(os.getenv('EONET_POLL_SECONDS', '600'))
    request_timeout_seconds: float = float(os.getenv('REQUEST_TIMEOUT_SECONDS', '20'))
    database_path: str = os.getenv('DATABASE_PATH', 'data/disaster_monitor.db')
    outbox_path: str = os.getenv('OUTBOX_PATH', 'outbox')
    user_agent: str = os.getenv('NWS_USER_AGENT', 'DisasterMonitor/0.1 (set-contact-in-env)')
    eonet_days: int = int(os.getenv('EONET_DAYS', '30'))
    lifecycle_poll_seconds: int = int(os.getenv('LIFECYCLE_POLL_SECONDS', '60'))
    end_grace_minutes: int = int(os.getenv('END_GRACE_MINUTES', '30'))
    collection_grace_hours: int = int(os.getenv('COLLECTION_GRACE_HOURS', '24'))

settings = Settings()
