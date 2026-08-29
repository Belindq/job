#!/bin/zsh
set -eu

PROJECT_DIR="${0:A:h:h}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.local.summer2027-job-hunter.plist"
RUNTIME_DIR="$HOME/Library/Application Support/Summer2027JobHunter"

if [[ ! -f "$PROJECT_DIR/config.json" || ! -f "$PROJECT_DIR/profile/resume.txt" ]]; then
  echo "Setup required before scheduling:" >&2
  echo "  cp config.example.json config.json" >&2
  echo "  cp profile/resume.example.txt profile/resume.txt" >&2
  echo "Then edit both files and run this installer again." >&2
  exit 2
fi

mkdir -p \
  "$HOME/Library/LaunchAgents" \
  "$RUNTIME_DIR/src" \
  "$RUNTIME_DIR/scripts" \
  "$RUNTIME_DIR/profile" \
  "$RUNTIME_DIR/config" \
  "$RUNTIME_DIR/output/pdf" \
  "$RUNTIME_DIR/state" \
  "$RUNTIME_DIR/logs"

# LaunchAgents are blocked by macOS privacy controls from opening scripts in
# Documents. Install a private runtime copy under Application Support instead.
cp "$PROJECT_DIR/src/job_hunter.py" "$RUNTIME_DIR/src/job_hunter.py"
cp "$PROJECT_DIR/src/company_boards.py" "$RUNTIME_DIR/src/company_boards.py"
cp "$PROJECT_DIR/scripts/run_daily.sh" "$RUNTIME_DIR/scripts/run_daily.sh"
cp "$PROJECT_DIR/scripts/email_report.py" "$RUNTIME_DIR/scripts/email_report.py"
cp "$PROJECT_DIR/company_boards.json" "$RUNTIME_DIR/company_boards.json"
cp "$PROJECT_DIR/config.json" "$RUNTIME_DIR/config.json"
cp "$PROJECT_DIR/profile/resume.txt" "$RUNTIME_DIR/profile/resume.txt"
if [[ -f "$PROJECT_DIR/config/email.env" ]]; then
  cp "$PROJECT_DIR/config/email.env" "$RUNTIME_DIR/config/email.env"
  chmod 600 "$RUNTIME_DIR/config/email.env"
fi
chmod 700 "$RUNTIME_DIR/scripts/run_daily.sh" "$RUNTIME_DIR/scripts/email_report.py"

# Seed the private runtime once, then keep the familiar workspace paths linked
# to the output that the background job can update.
if [[ -f "$PROJECT_DIR/state/jobs.json" && ! -f "$RUNTIME_DIR/state/jobs.json" ]]; then
  cp "$PROJECT_DIR/state/jobs.json" "$RUNTIME_DIR/state/jobs.json"
fi
if [[ -f "$PROJECT_DIR/output/jobs.json" && ! -L "$PROJECT_DIR/output/jobs.json" ]]; then
  cp "$PROJECT_DIR/output/jobs.json" "$RUNTIME_DIR/output/jobs.json"
fi
if [[ -f "$PROJECT_DIR/output/report.html" && ! -L "$PROJECT_DIR/output/report.html" ]]; then
  cp "$PROJECT_DIR/output/report.html" "$RUNTIME_DIR/output/report.html"
fi

mkdir -p "$PROJECT_DIR/output"
ln -sfn "$RUNTIME_DIR/output/report.html" "$PROJECT_DIR/output/report.html"
ln -sfn "$RUNTIME_DIR/output/jobs.json" "$PROJECT_DIR/output/jobs.json"
if [[ -d "$PROJECT_DIR/output/pdf" && ! -L "$PROJECT_DIR/output/pdf" ]]; then
  mv "$PROJECT_DIR/output/pdf" "$PROJECT_DIR/output/pdf.before-background-runtime"
fi
ln -sfn "$RUNTIME_DIR/output/pdf" "$PROJECT_DIR/output/pdf"
if [[ -d "$PROJECT_DIR/state" && ! -L "$PROJECT_DIR/state" ]]; then
  mv "$PROJECT_DIR/state" "$PROJECT_DIR/state.before-background-runtime"
fi
ln -sfn "$RUNTIME_DIR/state" "$PROJECT_DIR/state"
if [[ -d "$PROJECT_DIR/logs" && ! -L "$PROJECT_DIR/logs" ]]; then
  mv "$PROJECT_DIR/logs" "$PROJECT_DIR/logs.before-background-runtime"
fi
ln -sfn "$RUNTIME_DIR/logs" "$PROJECT_DIR/logs"

sed "s|__PROJECT_DIR__|$RUNTIME_DIR|g" "$PROJECT_DIR/scripts/com.local.summer2027-job-hunter.plist.template" > "$PLIST_PATH"
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "Installed daily 8:00 a.m. job search: $PLIST_PATH"
echo "Background runtime: $RUNTIME_DIR"
echo "Run once now with: $RUNTIME_DIR/scripts/run_daily.sh"
