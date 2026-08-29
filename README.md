# Internship Job Hunter

This is a local job-search tool for students. It searches public LinkedIn listings and 50 direct company job boards, removes duplicates, enforces your configured filters, and ranks the results against **your resume and job-search goals**.

## Features

- Searches LinkedIn public guest listings plus public Greenhouse, Ashby, Lever, Riot, and structured company career pages.
- Checks 50 configured employers, including Figma, Notion, Roblox, Riot Games, FAANG, and other major technology companies.
- Filters by Canada, United States, remote status, posting age, target season, internship/co-op title, title keywords, blocked employers, minimum score, and report size.
- Excludes mixed seasons such as `Summer/Fall 2027` when strict season filtering is enabled.
- Ranks matches using 60% resume fit and 40% career-goal fit, with a ranked top 10 at the beginning.
- Retains and deduplicates prior results while reapplying current filters to saved history.
- Generates `output/report.html`, `output/jobs.json`, and a polished PDF with real clickable application links.
- Runs every morning at 8:00 a.m. through a macOS LaunchAgent or Windows Task Scheduler and can email the PDF automatically.
- Keeps the resume, email password, and personalized configuration out of Git.

The company list is mostly technology-focused. Someone searching another field should customize both the search phrases and employer list.

## What you need

- A Mac or Windows computer with Python 3; PDF email generation also needs ReportLab
- This project folder
- A plain-text copy of your resume
- About 10 minutes to edit the search settings

Searching and HTML generation require no account login. Email delivery requires SMTP credentials, and LinkedIn access remains limited to public guest pages.

## First-time setup

On macOS, open **Terminal**, move into the project folder, and run:

```bash
cd /path/to/jobhunter
cp config.example.json config.json
cp profile/resume.example.txt profile/resume.txt
python3 -m pip install reportlab
```

Replace `/path/to/jobhunter` with the folder's actual location. You can also type `cd ` (with a space) and drag the project folder into Terminal.

On Windows, open **PowerShell**, move into the project folder, and run:

```powershell
cd C:\path\to\jobhunter
Copy-Item config.example.json config.json
Copy-Item profile\resume.example.txt profile\resume.txt
py -3 -m pip install reportlab
```

Replace `C:\path\to\jobhunter` with the folder's actual location.

### 1. Add your resume

Open `profile/resume.txt`, delete the example text, and paste the plain text of your resume. Include your education, projects, work experience, tools, technical skills, and accomplishments. Do not paste a PDF file into this text file; copy the text from it instead.

The resume is only used locally to calculate match scores. It is not uploaded by this program.

### 2. Configure searches, filters, and ranking

Open `config.json` and edit these fields:

- `locations`: cities or regions where you want to work.
- `searches`: phrases sent to the job search. Include the job titles you actually want.
- `filters`: hard inclusion/exclusion rules applied to new results and saved history.
- `goals.target_roles`: titles that should receive a strong preference.
- `goals.preferred_keywords`: skills or subjects that make a job more interesting.
- `goals.avoid_keywords`: words that should lower a match, such as `senior` or `full-time only`.
- `goals.target_season`: the season and year you are looking for.
- `blocked_companies`: employers to exclude.
- `excluded_seasons`: seasons to remove completely. Winter, Fall/Autumn, and Spring 2027 are excluded by default so mixed-season postings do not enter a Summer-only report.

`locations` controls which LinkedIn searches are requested. `filters.countries` controls which jobs from **every source** are allowed into the final report. Disabled countries are also removed from the LinkedIn query list to avoid unnecessary requests.

### Filter configuration

```json
"filters": {
  "countries": {
    "canada": true,
    "united_states": true
  },
  "include_remote": true,
  "include_unknown_locations": false,
  "posted_within_days": 45,
  "include_unknown_posted_date": true,
  "require_internship_in_title": true,
  "require_target_season_in_title": true,
  "exclude_mixed_seasons": true,
  "include_title_keywords": [],
  "exclude_title_keywords": [],
  "minimum_match_score": 0,
  "max_jobs_in_report": 200
}
```

| Setting | Effect |
| --- | --- |
| `countries.canada` | Includes recognized Canadian locations and enables Canadian LinkedIn search locations. |
| `countries.united_states` | Includes recognized U.S. locations and enables U.S. LinkedIn search locations. |
| `include_remote` | Includes remote/distributed jobs. Country-specific remote roles still respect the country toggles. |
| `include_unknown_locations` | Keeps listings whose location cannot be identified as Canada, U.S., or remote. Keep this `false` for strict geography. |
| `posted_within_days` | Keeps jobs posted within this many days and sends the same time window to LinkedIn. Use `null` to disable the age cutoff. |
| `include_unknown_posted_date` | Keeps company-board jobs that do not publish a reliable date. Set `false` for a strict date-only report. |
| `require_internship_in_title` | Requires `intern`, `internship`, or `co-op` in the title. |
| `require_target_season_in_title` | Requires the season/year from `goals.target_season` in the title, including formats such as `Summer '27`. |
| `exclude_mixed_seasons` | Applies `excluded_seasons` to titles, removing combinations such as `Summer/Fall 2027`. |
| `include_title_keywords` | If non-empty, a title must contain at least one listed phrase. Example: `["software", "product design"]`. |
| `exclude_title_keywords` | Removes titles containing any listed phrase. Example: `["phd", "hardware"]`. |
| `minimum_match_score` | Removes jobs below this 0-100 overall match score after ranking. |
| `max_jobs_in_report` | Caps the number of highest-ranked jobs in HTML, JSON, and PDF. Use `null` for no cap. |

Examples:

- Canada only: set `canada` to `true` and `united_states` to `false`.
- U.S. only: set `canada` to `false` and `united_states` to `true`.
- Posted in the last week: set `posted_within_days` to `7`.
- Strictly dated listings: set `include_unknown_posted_date` to `false`.
- Only software/design roles: set `include_title_keywords` to `["software", "frontend", "design engineer", "product design", "ui", "ux"]`.

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

After changing `config.json`, `profile/resume.txt`, company boards, or runtime code on macOS, rerun `./scripts/install_launchd.sh`. The installer copies the current setup into the background-safe runtime used by the 8:00 a.m. schedule.

On Windows, the scheduled task reads the project files directly, so saved changes are used on its next run.

### 3. Optional: update the employer list

The companies checked directly are in `company_boards.json`. They are mostly technology companies. You can edit this file to add an employer's public Greenhouse, Ashby, Lever, or structured careers-page feed, but this may require technical setup. LinkedIn public search results are still collected from the phrases in `config.json`.

## Configure email delivery

The daily script can email a PDF version of the finished report. Gmail requires an **App Password** for this; do not use your normal Gmail password.

1. Turn on 2-Step Verification for the Gmail account that will send the message.
2. Create an App Password in your Google Account security settings.
3. On macOS, copy and open the example settings:

	```bash
	cp config/email.env.example config/email.env
	open -e config/email.env
	```

   On Windows, use PowerShell:

	```powershell
	Copy-Item config\email.env.example config\email.env
	notepad config\email.env
	```

4. Replace `SMTP_PASSWORD` with the 16-character App Password. Set `SMTP_USERNAME` to the sending Gmail address and `EMAIL_TO` to the address that should receive the report. The provided example sends to `unicornbelinda@gmail.com`.

The secret file is ignored by Git and is not uploaded. The email script builds `output/pdf/job-report.pdf`; every job title and **Open actual job posting** label links to the real application page. It does not send your resume or `config.json`. The local HTML report keeps the richer visual formatting.

After enabling email on macOS, reinstall the schedule so it receives the new secret file:

```bash
./scripts/install_launchd.sh
```

On Windows, the scheduled task reads `config\email.env` directly; no reinstall is needed.

Test email delivery on macOS without waiting until 8:00 a.m.:

```bash
python3 scripts/email_report.py
```

On Windows, use PowerShell:

```powershell
py -3 scripts\email_report.py
```

Email errors are recorded in `logs/email.log`.

## Run a real search once

On macOS:

```bash
./scripts/run_daily.sh
open output/report.html
```

On Windows, use PowerShell. The second command sends the email only when `config\email.env` exists:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
py -3 src\job_hunter.py *>> logs\job-hunter.log
if (Test-Path config\email.env) { py -3 scripts\email_report.py *>> logs\email.log }
Start-Process output\report.html
```

The first run may take a few minutes because the tool pauses between requests and fetches job descriptions. Results are saved in `output/report.html` and `output/jobs.json`; diagnostic messages are saved in `logs/job-hunter.log`.

To collect only one source on macOS:

```bash
python3 src/job_hunter.py --skip-linkedin       # company boards only
python3 src/job_hunter.py --skip-company-boards # LinkedIn only
```

On Windows, use PowerShell:

```powershell
py -3 src\job_hunter.py --skip-linkedin
py -3 src\job_hunter.py --skip-company-boards
```

## Run it automatically every day (macOS)

After completing the setup above:

```bash
./scripts/install_launchd.sh
```

This schedules a search for 8:00 a.m. each day. The Mac must be awake or logged in around that time; macOS normally runs a missed job after wake/login.

The installer keeps its background-safe runtime under `~/Library/Application Support/Summer2027JobHunter`. macOS blocks LaunchAgents from opening scripts inside `Documents`; the workspace report, state, PDF, and log paths are linked to the private runtime so existing bookmarks keep working.

To remove the schedule without deleting reports:

```bash
./scripts/uninstall_launchd.sh
```

## Run it automatically every day (Windows)

After completing the setup above:

1. Open **Task Scheduler** from the Start menu and select **Create Basic Task**.
2. Name it `Summer 2027 Job Hunter`.
3. Choose **Daily**, set the start time to **8:00 AM**, and choose **Start a program**.
4. Set **Program/script** to `powershell.exe`.
5. Set **Add arguments** to the following, replacing the example project path with the full path to your checkout:

   ```text
   -NoProfile -ExecutionPolicy Bypass -Command "Set-Location 'C:\path\to\jobhunter'; New-Item -ItemType Directory -Force logs | Out-Null; py -3 src\job_hunter.py *>> logs\job-hunter.log; if (Test-Path config\email.env) { py -3 scripts\email_report.py *>> logs\email.log }"
   ```

6. Finish the wizard. In the task's **Properties**, enable **Run task as soon as possible after a scheduled start is missed** if you want a sleeping computer to catch up after it wakes.

The computer must be on at 8:00 a.m. or wake later with the missed-run option enabled. To test it, right-click the task and choose **Run**. To disable the automation without deleting reports, right-click the task and choose **Disable** or **Delete**.

## Troubleshooting and limits

- If setup says a file is missing, confirm that `config.json` and `profile/resume.txt` were created from the example files.
- If there are no useful results, broaden `locations` and `searches`, enable `include_unknown_locations` or `include_unknown_posted_date`, increase `posted_within_days`, and review title/score filters.
- With the default strict settings, every retained posting must identify itself as an internship/co-op and explicitly name the target season in its title.
- Posting dates are not available from every company board. `include_unknown_posted_date` controls whether those jobs survive the date filter.
- A company-board failure appears as a warning; other sources can still complete.
- LinkedIn can rate-limit or change its public guest pages. The tool records warnings and does not log in, bypass CAPTCHAs, or evade access controls.
- Automated access may be restricted by LinkedIn's current terms. Review those terms before enabling the schedule.
- Results are retained locally so a temporary network failure does not unexpectedly erase the report.
