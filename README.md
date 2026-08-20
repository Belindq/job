# Internship Job Hunter

This is a small, local job-search tool for students. It searches public job listings, removes duplicates, and ranks the results against **your resume and your job-search preferences**. Company-board results are limited to internship and co-op postings; LinkedIn results are ranked but are not perfectly filtered. It creates a readable HTML report at `output/report.html`.

It can be shared with a friend in mechanical engineering, but they should customize the search settings first. The included company list is mostly large technology companies, so it is a starting point rather than a complete mechanical-engineering job database.

## What you need

- A Mac with Python 3 (`python3` in Terminal)
- This project folder
- A plain-text copy of your resume
- About 10 minutes to edit the search settings

No Python packages or account logins are required.

## First-time setup

Open **Terminal**, move into the project folder, and run:

```bash
cd /path/to/jobhunter
cp config.example.json config.json
cp profile/resume.example.txt profile/resume.txt
```

Replace `/path/to/jobhunter` with the folder's actual location. You can also type `cd ` (with a space) and drag the project folder into Terminal.

### 1. Add your resume

Open `profile/resume.txt`, delete the example text, and paste the plain text of your resume. Include your education, projects, work experience, tools, technical skills, and accomplishments. Do not paste a PDF file into this text file; copy the text from it instead.

The resume is only used locally to calculate match scores. It is not uploaded by this program.

### 2. Choose the searches

Open `config.json` and edit these fields:

- `locations`: cities or regions where you want to work.
- `searches`: phrases sent to the job search. Include the job titles you actually want.
- `goals.target_roles`: titles that should receive a strong preference.
- `goals.preferred_keywords`: skills or subjects that make a job more interesting.
- `goals.avoid_keywords`: words that should lower a match, such as `senior` or `full-time only`.
- `goals.target_season`: the season and year you are looking for.
- `blocked_companies`: employers to exclude.

For example, a mechanical-engineering student might use settings like these:

```json
"searches": [
	"summer 2027 mechanical engineering intern",
	"2027 manufacturing engineering internship",
	"2027 robotics engineering co-op",
	"2027 product design engineering intern",
	"2027 test engineering internship"
],
"goals": {
	"target_roles": [
		"mechanical engineering intern",
		"manufacturing engineering intern",
		"robotics engineering co-op"
	],
	"preferred_locations": ["Toronto", "Vancouver", "Remote"],
	"preferred_keywords": [
		"CAD", "SolidWorks", "Creo", "FEA",
		"manufacturing", "robotics", "prototyping", "thermodynamics"
	],
	"avoid_keywords": ["senior", "staff", "principal", "manager", "full-time only"],
	"must_be_internship": true,
	"target_season": "summer 2027"
}
```

Use ordinary text in `preferred_keywords`; add the tools and subjects that matter for your field. Keep valid JSON formatting: use double quotes, commas between items, and no comma after the final item.

The scoring is a guide, not a hiring decision. Results are ranked using **60% resume fit and 40% goal fit**. A high score means the posting resembles the resume and preferences you entered.

### 3. Optional: update the employer list

The companies checked directly are in `company_boards.json`. They are mostly technology companies. You can edit this file to add an employer's public Greenhouse, Ashby, Lever, or structured careers-page feed, but this may require technical setup. LinkedIn public search results are still collected from the phrases in `config.json`.

## Try it without using the internet

This verifies that Python can run and shows the report format using intentionally fake listings:

```bash
python3 src/job_hunter.py --fixture tests/fixtures/jobs.json
open output/demo/report.html
```

The demo is isolated under `output/demo/` and does not change your real report or saved job history.

## Run a real search once

```bash
./scripts/run_daily.sh
open output/report.html
```

The first run may take a few minutes because the tool pauses between requests and fetches job descriptions. Results are saved in `output/report.html` and `output/jobs.json`; diagnostic messages are saved in `logs/job-hunter.log`.

To collect only one source:

```bash
python3 src/job_hunter.py --skip-linkedin       # company boards only
python3 src/job_hunter.py --skip-company-boards # LinkedIn only
```

## Run it automatically every day (macOS)

After completing the setup above:

```bash
./scripts/install_launchd.sh
```

This schedules a search for 8:00 a.m. each day. The Mac must be awake or logged in around that time; macOS normally runs a missed job after wake/login. To remove the schedule without deleting reports:

```bash
./scripts/uninstall_launchd.sh
```

## Troubleshooting and limits

- If setup says a file is missing, confirm that `config.json` and `profile/resume.txt` were created from the example files.
- If there are no useful results, broaden `locations` and `searches`, check that `target_season` matches the listings, and remove overly specific keywords.
- Only postings containing internship or co-op language are included by the company-board collectors.
- A company-board failure appears as a warning; other sources can still complete.
- LinkedIn can rate-limit or change its public guest pages. The tool records warnings and does not log in, bypass CAPTCHAs, or evade access controls.
- Automated access may be restricted by LinkedIn's current terms. Review those terms before enabling the schedule.
- Results are retained locally so a temporary network failure does not unexpectedly erase the report.
