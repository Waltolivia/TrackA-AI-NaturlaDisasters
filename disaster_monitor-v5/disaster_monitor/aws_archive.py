"""Tiered storage for the disaster monitor.

The local SQLite database plus the human-readable ``archive/`` reports are the
working set. Recent data (``LOCAL_RETENTION_DAYS``, one week by default) stays
on the collector machine. Finished events that are older than the retention
window are copied to Amazon DynamoDB and are only removed locally *after* the
remote write has succeeded, so a network or credential problem can never lose
data.

Why DynamoDB (simplest and cheapest AWS database for this workload):

* fully managed -- nothing to run, no VPC, no security group, no connection
  string or driver to configure,
* ``PAY_PER_REQUEST`` (on-demand) billing -- no capacity planning and nothing
  to pay while the monitor is idle,
* the write volume here is only a few hundred small items per day, which is
  covered by the AWS always-free tier, so the cost is effectively zero.

Design
------
One DynamoDB table holds every row of every archived event. All items of an
event share one partition key (``pk = EVENT#<public_id>``) and are separated by
the sort key (``sk``):

    pk                    sk                                meaning
    EVENT#EVT-00000001    META                              events row
    EVENT#EVT-00000001    ALERT#<source>#<source_id>        alerts row
    EVENT#EVT-00000001    LINK#<source>#<source_event_id>   source_links row
    EVENT#EVT-00000001    REVIEW#<id>                       review_queue row
    EVENT#EVT-00000001    REPORT                            rendered text report
"""

import json
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .archive import event_report_path

log = logging.getLogger('disaster-monitor')

DEFAULT_TABLE_NAME = 'disaster_monitor_history'


class AwsArchiveError(RuntimeError):
    """Raised when the AWS archive cannot be configured or reached."""


def _dynamodb_resource(region, session=None):
    """Build a boto3 DynamoDB resource, importing boto3 only when needed."""
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise AwsArchiveError(
            "boto3 is required for AWS archiving; install it with "
            "`pip install boto3` (or `pip install -r requirements.txt`)"
        ) from exc
    factory = session or boto3
    return factory.resource('dynamodb', region_name=region)


def _value(value):
    """Convert one SQLite value into a DynamoDB-safe attribute value.

    DynamoDB rejects native floats, so they are stored as ``Decimal``. The
    ``raw_json``/``geometry_json`` columns are already JSON text and are kept
    verbatim so no source detail is lost.
    """
    if value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return json.dumps(value, sort_keys=True, default=str)


def _is_missing_table(exc):
    response = getattr(exc, 'response', None)
    if isinstance(response, dict):
        code = (response.get('Error') or {}).get('Code')
        if code in {'ResourceNotFoundException', 'TableNotFoundException'}:
            return True
    return type(exc).__name__ == 'ResourceNotFoundException'


def _row_attributes(row):
    return {key: _value(value) for key, value in dict(row).items()}


def event_items(db, event, report_path=None):
    """Build every DynamoDB item that represents one archived event."""
    pk = f'EVENT#{event["public_id"]}'
    items = [dict(pk=pk, sk='META', record_type='event', **_row_attributes(event))]
    for alert in db.alerts_for_event(event['id']):
        row = _row_attributes(alert)
        items.append(dict(pk=pk, sk=f'ALERT#{row["source"]}#{row["source_id"]}', record_type='alert', **row))
    for link in db.source_links_for_event(event['id']):
        row = _row_attributes(link)
        items.append(dict(pk=pk, sk=f'LINK#{row["source"]}#{row["source_event_id"]}', record_type='source_link', **row))
    for review in db.review_rows_for_event(event['id']):
        row = _row_attributes(review)
        items.append(dict(pk=pk, sk=f'REVIEW#{row["id"]}', record_type='review', **row))
    if report_path is not None:
        report = Path(report_path)
        if report.is_file():
            items.append(dict(pk=pk, sk='REPORT', record_type='report', text=report.read_text(encoding='utf-8')))
    return items


def _prune_empty_dirs(folder, root):
    """Remove emptied archive folders, stopping at the archive root."""
    root_path = Path(root).resolve()
    current = Path(folder).resolve()
    while current != root_path and root_path in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


class AwsArchiver:
    """Copy finished events older than the local window to AWS DynamoDB."""

    def __init__(self, *, region, table_name=DEFAULT_TABLE_NAME, retention_days=7, resource=None):
        self.region = region
        self.table_name = table_name
        self.retention_days = retention_days
        self._resource = resource

    @property
    def resource(self):
        if self._resource is None:
            self._resource = _dynamodb_resource(self.region)
        return self._resource

    @property
    def table(self):
        return self.resource.Table(self.table_name)

    def ensure_table(self):
        """Create the archive table on demand. Returns True when it was created."""
        client = self.resource.meta.client
        try:
            client.describe_table(TableName=self.table_name)
            return False
        except Exception as exc:  # noqa: BLE001 - re-raised unless it means "missing"
            if not _is_missing_table(exc):
                raise
        client.create_table(
            TableName=self.table_name,
            BillingMode='PAY_PER_REQUEST',
            KeySchema=[
                {'AttributeName': 'pk', 'KeyType': 'HASH'},
                {'AttributeName': 'sk', 'KeyType': 'RANGE'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'pk', 'AttributeType': 'S'},
                {'AttributeName': 'sk', 'AttributeType': 'S'},
            ],
        )
        log.info('created DynamoDB archive table %s', self.table_name)
        return True

    def _cutoff(self, now=None):
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment - timedelta(days=self.retention_days)

    def pending(self, db, *, now=None, limit=None):
        """Describe the finished events that are older than the local window."""
        cutoff = self._cutoff(now)
        events = db.events_ready_for_archive(cutoff.isoformat(), limit)
        return {
            'retention_days': self.retention_days,
            'cutoff': cutoff.isoformat(),
            'table': self.table_name,
            'region': self.region,
            'event_count': len(events),
            'events': [
                {
                    'public_id': event['public_id'],
                    'event_id': event['id'],
                    'status': event['status'],
                    'ended_at': event['ended_at'],
                    'collection_complete_at': event['collection_complete_at'],
                }
                for event in events
            ],
        }

    def archive(self, db, *, archive_path='archive', now=None, limit=None, create_table=True):
        """Move every eligible event to DynamoDB, then delete it locally.

        Each event is written in full before anything is deleted. If one event
        fails, it is left untouched locally and reported in ``last_error`` so it
        can be retried on the next run.
        """
        cutoff = self._cutoff(now)
        if create_table:
            self.ensure_table()
        table = self.table
        events = db.events_ready_for_archive(cutoff.isoformat(), limit)

        archived = failed = items_written = reports_removed = 0
        last_error = None
        for event in events:
            report_path = event_report_path(event, archive_path)
            try:
                items = event_items(db, event, report_path)
                for item in items:
                    table.put_item(Item=item)
            except Exception as exc:  # noqa: BLE001 - one bad event must not stop the rest
                failed += 1
                last_error = f'{type(exc).__name__}: {exc}'
                log.warning('aws archive failed for %s: %s', event['public_id'], last_error)
                continue

            db.delete_event(event['id'])
            if report_path.is_file():
                report_path.unlink()
                reports_removed += 1
                _prune_empty_dirs(report_path.parent, archive_path)
            archived += 1
            items_written += len(items)

        result = {
            'retention_days': self.retention_days,
            'cutoff': cutoff.isoformat(),
            'table': self.table_name,
            'region': self.region,
            'events_eligible': len(events),
            'events_archived': archived,
            'events_failed': failed,
            'items_written': items_written,
            'reports_removed': reports_removed,
            'last_error': last_error,
        }
        if archived or failed:
            log.info('aws archive result=%s', result)
        return result


