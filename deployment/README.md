# Unattended Linux deployment

These templates run the frozen collector and worker continuously on a BYU VM,
small cloud VM, or Raspberry Pi using `systemd`. Test both commands manually
before enabling automatic startup.

The examples assume:

- repository: `/opt/tracka`
- service account: `tracka`
- provider secrets: `/etc/tracka/providers.env`
- collector settings: `/etc/tracka/collector.env`

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
sudo -u tracka git checkout study-v1.0.0

sudo -u tracka uv sync --project pipeline_worker --extra providers
cd disaster_monitor-v5
sudo -u tracka uv venv --python 3.11
sudo -u tracka uv pip install -r requirements.txt
```

Do not deploy `study-v1.0.0` until the team has created that tag.

## 2. Install secrets and settings

Copy the examples, insert the real values, and restrict access:

```bash
sudo cp deployment/systemd/providers.env.example /etc/tracka/providers.env
sudo cp deployment/systemd/collector.env.example /etc/tracka/collector.env
sudo chmod 600 /etc/tracka/providers.env /etc/tracka/collector.env
sudo chown root:root /etc/tracka/providers.env /etc/tracka/collector.env
```

Never commit either completed environment file.

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
- Disk space, provider balances, and Google free-tier quota remain available.
- Databases and completed results reached the off-machine backup destination.

Use exactly one worker service. Running multiple workers with separate state
databases can duplicate paid probes.
