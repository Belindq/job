#!/bin/zsh
set -eu

PROJECT_DIR="${0:A:h:h}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.local.summer2027-job-hunter.plist"

if [[ ! -f "$PROJECT_DIR/config.json" || ! -f "$PROJECT_DIR/profile/resume.txt" ]]; then
  echo "Setup required before scheduling:" >&2
  echo "  cp config.example.json config.json" >&2
  echo "  cp profile/resume.example.txt profile/resume.txt" >&2
  echo "Then edit both files and run this installer again." >&2
  exit 2
fi

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"

sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$PROJECT_DIR/scripts/com.local.summer2027-job-hunter.plist.template" > "$PLIST_PATH"
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "Installed daily 8:00 a.m. job search: $PLIST_PATH"
echo "Run once now with: $PROJECT_DIR/scripts/run_daily.sh"
