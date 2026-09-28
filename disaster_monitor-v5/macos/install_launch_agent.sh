#!/bin/bash
set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "$NWS_USER_AGENT" ]; then echo 'Set NWS_USER_AGENT first, e.g. export NWS_USER_AGENT="DisasterMonitor/0.3 (you@example.com)"'; exit 1; fi
mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs" "$PROJECT_DIR/data" "$PROJECT_DIR/backups" "$PROJECT_DIR/outbox"
sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__NWS_USER_AGENT__|$NWS_USER_AGENT|g" "$PROJECT_DIR/macos/com.disastermonitor.plist.template" > "$HOME/Library/LaunchAgents/com.disastermonitor.plist"
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.disastermonitor.plist" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.disastermonitor.plist"
launchctl enable "gui/$(id -u)/com.disastermonitor"
echo "Installed. Check: launchctl print gui/$(id -u)/com.disastermonitor"
