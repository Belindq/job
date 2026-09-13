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

for PROFILE_DIR in profiles/*(N/); do
	PROFILE_NAME="${PROFILE_DIR:t}"
	if [[ ! -f "$PROFILE_DIR/config.json" || ! -f "$PROFILE_DIR/resume.txt" ]]; then
		print -u2 "Skipping incomplete profile: $PROFILE_NAME"
		continue
	fi
	PROFILE_OUTPUT="output/profiles/$PROFILE_NAME"
	PROFILE_STATE="state/profiles/$PROFILE_NAME"
	mkdir -p "$PROFILE_OUTPUT/pdf" "$PROFILE_STATE"
	"$PYTHON" src/job_hunter.py \
		--config "$PROFILE_DIR/config.json" \
		--resume "$PROFILE_DIR/resume.txt" \
		--output "$PROFILE_OUTPUT" \
		--state "$PROFILE_STATE/jobs.json" \
		>> "logs/job-hunter-$PROFILE_NAME.log" 2>&1
	if [[ -f "$PROFILE_DIR/email.env" ]]; then
		"$PDF_PYTHON" scripts/email_report.py \
			--env "$PROFILE_DIR/email.env" \
			--jobs "$PROFILE_OUTPUT/jobs.json" \
			--pdf "$PROFILE_OUTPUT/pdf/job-report.pdf" \
			--sent-state "$PROFILE_STATE/email-sent.json" \
			--profile-name "$PROFILE_NAME" \
			>> "logs/email-$PROFILE_NAME.log" 2>&1
	fi
done
