#!/bin/zsh
set -eu

PLIST_PATH="$HOME/Library/LaunchAgents/com.local.summer2027-job-hunter.plist"
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
if [[ -f "$PLIST_PATH" ]]; then
  mv "$PLIST_PATH" "$HOME/.Trash/"
fi
echo "Removed the daily job-search schedule. Existing reports were kept."

