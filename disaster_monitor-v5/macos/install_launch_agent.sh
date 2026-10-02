#!/bin/bash
set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "$NWS_USER_AGENT" ]; then echo 'Set NWS_USER_AGENT first, e.g. export NWS_USER_AGENT="DisasterMonitor/0.3 (you@example.com)"'; exit 1; fi
if [ ! -x "$PROJECT_DIR/.venv/bin/python" ]; then
	echo "Missing virtual environment at $PROJECT_DIR/.venv. Create it and install requirements first." >&2
	exit 1
fi
mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs" "$PROJECT_DIR/data" "$PROJECT_DIR/backups" "$PROJECT_DIR/outbox"
PLIST_PATH="$HOME/Library/LaunchAgents/com.disastermonitor.plist"
PROJECT_DIR="$PROJECT_DIR" NWS_USER_AGENT="$NWS_USER_AGENT" PLIST_PATH="$PLIST_PATH" python3 - <<'PY'
import os
from pathlib import Path
from xml.sax.saxutils import escape

template = Path(os.environ['PROJECT_DIR']) / 'macos' / 'com.disastermonitor.plist.template'
text = template.read_text()
text = text.replace('__PROJECT_DIR__', escape(os.environ['PROJECT_DIR']))
text = text.replace('__NWS_USER_AGENT__', escape(os.environ['NWS_USER_AGENT']))
Path(os.environ['PLIST_PATH']).write_text(text)
PY
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.disastermonitor.plist" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.disastermonitor.plist"
launchctl enable "gui/$(id -u)/com.disastermonitor"
echo "Installed. Check: launchctl print gui/$(id -u)/com.disastermonitor"
