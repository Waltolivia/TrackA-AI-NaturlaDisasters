"""Manually inspect or run the AWS tiered-storage archive.

    python -m disaster_monitor.archive_cli status
    python -m disaster_monitor.archive_cli run --dry-run
    python -m disaster_monitor.archive_cli run
"""

import argparse
import json

from .aws_archive import AwsArchiver
from .config import settings
from .database import Database


def build_archiver(retention_days=None):
    return AwsArchiver(
        table_name=settings.aws_dynamodb_table,
        region=settings.aws_region,
        retention_days=settings.local_retention_days if retention_days is None else retention_days,
    )


def parser():
    ap = argparse.ArgumentParser(description='Show or run the AWS tiered-storage archive')
    sub = ap.add_subparsers(dest='cmd', required=True)
    status = sub.add_parser('status', help='List finished events that are ready to move to AWS')
    status.add_argument('--retention-days', type=int, default=None)
    status.add_argument('--limit', type=int, default=None)
    run = sub.add_parser('run', help='Copy old data to AWS, then delete it locally')
    run.add_argument('--retention-days', type=int, default=None)
    run.add_argument('--limit', type=int, default=None)
    run.add_argument('--dry-run', action='store_true', help='Report what would move without writing to AWS')
    return ap


def main():
    args = parser().parse_args()
    db = Database(settings.database_path)
    archiver = build_archiver(args.retention_days)
    if args.cmd == 'status' or args.dry_run:
        print(json.dumps(archiver.pending(db, limit=args.limit), indent=2))
        return
    print(json.dumps(archiver.archive(db, archive_path=settings.archive_path, limit=args.limit), indent=2))


if __name__ == '__main__':
    main()
