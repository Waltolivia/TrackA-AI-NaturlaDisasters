from dataclasses import dataclass
import os


def _enabled(name, *, legacy_name=None, default='false'):
    """Read one boolean flag while preserving an older environment name."""
    value = os.getenv(name)
    if value is None and legacy_name is not None:
        value = os.getenv(legacy_name)
    return (default if value is None else value).lower() in {'1','true','yes','on'}

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
    # Optional secondary retention tier: keep a rolling local window, then
    # move older finished ground-truth rows to Amazon DynamoDB. The older
    # AWS_ARCHIVE_ENABLED name remains an alias for existing deployments.
    local_retention_days: int = int(os.getenv('LOCAL_RETENTION_DAYS', '7'))
    dynamodb_archive_enabled: bool = _enabled(
        'DYNAMODB_ARCHIVE_ENABLED', legacy_name='AWS_ARCHIVE_ENABLED'
    )
    aws_region: str = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
    aws_dynamodb_table: str = os.getenv('AWS_DYNAMODB_TABLE', 'disaster_monitor_history')
    aws_archive_interval_hours: int = int(os.getenv('AWS_ARCHIVE_INTERVAL_HOURS', '24'))
    # Primary shared research archive. This immediately mirrors newly written
    # event snapshots to S3 and never removes the local working copy.
    s3_archive_enabled: bool = os.getenv('S3_ARCHIVE_ENABLED', 'false').lower() in {'1','true','yes','on'}
    s3_bucket: str = os.getenv('S3_BUCKET', '')
    s3_prefix: str = os.getenv('S3_PREFIX', 'disaster_monitor-v5/archive')
    s3_pending_path: str = os.getenv('S3_PENDING_PATH', 'data/s3_pending')
    s3_sync_seconds: float = float(os.getenv('S3_SYNC_SECONDS', '5'))
    s3_backfill_on_start: bool = _enabled('S3_BACKFILL_ON_START', default='true')

    @property
    def aws_archive_enabled(self):
        """Backward-compatible attribute for integrations using the old name."""
        return self.dynamodb_archive_enabled

settings = Settings()
