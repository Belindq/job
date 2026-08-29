#!/bin/zsh
set -eu

PLIST_PATH="$HOME/Library/LaunchAgents/com.local.summer2027-job-hunter.plist"
RUNTIME_DIR="$HOME/Library/Application Support/Summer2027JobHunter"
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
if [[ -f "$PLIST_PATH" ]]; then
  mv "$PLIST_PATH" "$HOME/.Trash/"
fi
echo "Removed the daily job-search schedule. Existing reports and runtime were kept at: $RUNTIME_DIR"
