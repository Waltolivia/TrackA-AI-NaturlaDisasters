# Unattended Linux deployment

These templates run the frozen collector and worker continuously on a BYU VM,
small cloud VM, or Raspberry Pi using `systemd`. Test both commands manually
before enabling automatic startup.

The examples assume:

- repository: `/opt/tracka`
- service account: `tracka`
- provider secrets: `/etc/tracka/providers.env`
- collector settings: `/etc/tracka/collector.env`

Create and test the private shared bucket first by following
[`S3_SETUP.md`](S3_SETUP.md). The collector and worker must use the same
`S3_BUCKET`, `S3_PREFIX`, and `AWS_REGION` values.

DynamoDB is not required. Leave `DYNAMODB_ARCHIVE_ENABLED=false` unless the
team has separately approved removing old completed ground-truth rows from
the VM after they are copied to DynamoDB.

Change those paths if the host uses a different layout.

## 1. Install

```bash
sudo useradd --system --create-home tracka
sudo mkdir -p /opt/tracka /etc/tracka
sudo chown -R tracka:tracka /opt/tracka

sudo -u tracka git clone \
  https://github.com/Waltolivia/TrackA-AI-NaturlaDisasters.git \
  /opt/tracka
cd /opt/tracka
sudo -u tracka git checkout study-v3.0.0

sudo -u tracka uv sync --project pipeline_worker --extra providers
cd disaster_monitor-v5
sudo -u tracka uv venv --python 3.11
sudo -u tracka uv pip install -r requirements.txt
```

Do not deploy `study-v3.0.0` until the team has approved and created that tag.

## 2. Install secrets and settings

Copy the examples, insert the real values, and restrict access:

```bash
sudo cp deployment/systemd/providers.env.example /etc/tracka/providers.env
sudo cp deployment/systemd/collector.env.example /etc/tracka/collector.env
sudo chmod 600 /etc/tracka/providers.env /etc/tracka/collector.env
sudo chown root:root /etc/tracka/providers.env /etc/tracka/collector.env
```

Never commit either completed environment file.

On an EC2 VM, attach an IAM instance role with the S3 uploader policy instead
of putting `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in these files. On a
BYU or other non-AWS VM, configure a dedicated least-privilege AWS identity for
the `tracka` service account.

## 3. Install services

```bash
sudo cp deployment/systemd/tracka-collector.service /etc/systemd/system/
sudo cp deployment/systemd/tracka-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tracka-collector tracka-worker
```

## 4. Monitor

```bash
systemctl status tracka-collector tracka-worker
journalctl -u tracka-collector -u tracka-worker -f
sudo -u tracka /opt/tracka/pipeline_worker/.venv/bin/pipeline-worker \
  status --limit 50
```

Check daily during the initial study:

- `disaster_monitor-v5/data/health.json` remains current.
- `outbox/pending/` and `outbox/failed/` do not grow unexpectedly.
- The worker has no unexplained `DEAD` jobs.
- Disk space, provider balances, Gemini search allowance, and billing budgets
  remain available.
- Databases and completed results reached the off-machine backup destination.
- Recent events contain adjacent weather and AI folders in the S3 bucket.

Use exactly one worker service. Running multiple workers with separate state
databases can duplicate paid probes.
