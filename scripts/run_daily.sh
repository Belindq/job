#!/bin/zsh
set -eu

PROJECT_DIR="${0:A:h:h}"
cd "$PROJECT_DIR"
mkdir -p logs

if [[ -x /opt/homebrew/bin/python3 ]]; then
	PYTHON=/opt/homebrew/bin/python3
else
	PYTHON=/usr/bin/python3
fi
PDF_PYTHON=/usr/bin/python3

"$PYTHON" src/job_hunter.py >> logs/job-hunter.log 2>&1

if [[ -f config/email.env ]]; then
	"$PDF_PYTHON" scripts/email_report.py >> logs/email.log 2>&1
fi
