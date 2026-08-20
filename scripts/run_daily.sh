#!/bin/zsh
set -eu

PROJECT_DIR="${0:A:h:h}"
cd "$PROJECT_DIR"
mkdir -p logs
/usr/bin/env python3 src/job_hunter.py >> logs/job-hunter.log 2>&1

