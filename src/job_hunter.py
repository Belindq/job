#!/usr/bin/env python3
"""Collect LinkedIn and company-board internships, then rank them against a resume and goals."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "in", "is", "it", "of", "on", "or", "our", "that", "the", "their", "this",
    "to", "we", "will", "with", "you", "your", "job", "role", "work", "team",
}
SKILL_TERMS = {
    "python", "javascript", "typescript", "java", "c++", "c#", "swift", "kotlin",
    "react", "next.js", "node", "node.js", "sql", "postgresql", "aws", "gcp",
    "azure", "docker", "kubernetes", "git", "figma", "sketch", "prototyping",
    "wireframing", "user research", "design systems", "product design", "ux", "ui",
    "frontend", "backend", "full stack", "machine learning", "data structures",
}
CANADA_MARKERS = {
    "canada", "ontario", "british columbia", "quebec", "alberta", "manitoba",
    "saskatchewan", "nova scotia", "new brunswick", "newfoundland", "pei",
    "toronto", "waterloo", "vancouver", "montreal", "ottawa", "calgary",
    "edmonton", "mississauga", "kitchener",
}
US_MARKERS = {
    "united states", "usa", "new york", "san francisco", "seattle", "boston",
    "austin", "los angeles", "chicago", "san jose", "palo alto", "bellevue",
    "menlo park", "mountain view", "washington, dc", "california", "texas",
    "massachusetts", "washington state", "illinois", "virginia", "colorado",
    "georgia", "florida", "pennsylvania", "north carolina", "new jersey",
}
CANADA_PROVINCE_CODES = "AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT"
US_STATE_CODES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    url: str
    posted: str = ""
    description: str = ""
    source: str = "LinkedIn"
    discovered_at: str = ""
    score: float = 0.0
    resume_fit: float = 0.0
    goal_fit: float = 0.0
    reasons: list[str] = field(default_factory=list)


class CardParser(HTMLParser):
    """Tolerant parser for LinkedIn's public guest job cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jobs: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "li" and self.current is None:
            self.current = {}
        if self.current is None:
            return
        if "base-card" in classes and values.get("data-entity-urn"):
            self.current["urn"] = values["data-entity-urn"] or ""
        if tag == "a" and ("base-card__full-link" in classes or "base-card__full-link" in (values.get("class") or "")):
            self.current["url"] = values.get("href") or ""
        mappings = {
            "base-search-card__title": "title",
            "base-search-card__subtitle": "company",
            "job-search-card__location": "location",
            "job-search-card__listdate": "posted",
        }
        for class_name, key in mappings.items():
            if class_name in classes:
                self.capture = key
        if tag == "time" and values.get("datetime"):
            self.current["posted"] = values["datetime"] or ""

    def handle_data(self, data: str) -> None:
        if self.current is not None and self.capture and data.strip():
            self.current[self.capture] = (self.current.get(self.capture, "") + " " + data.strip()).strip()

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        self.capture = None
        # A search result is one top-level <li>. Do not track arbitrary element
        # depth: LinkedIn's fragment includes void elements without end tags.
        if tag == "li":
            if self.current.get("title") and self.current.get("url"):
                self.jobs.append(self.current)
            self.current = None


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg"}:
            self.hidden += 1
        if tag in {"p", "li", "br", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.parts.append(data.strip() + " ")


def fetch(url: str, timeout: int = 25) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_url(url: str) -> str:
    return html.unescape(url).split("?")[0]


def job_id(card: dict[str, str]) -> str:
    urn_match = re.search(r"(\d+)$", card.get("urn", ""))
    url_match = re.search(r"-(\d+)(?:/)?$", normalize_url(card.get("url", "")))
    if urn_match or url_match:
        return (urn_match or url_match).group(1)  # type: ignore[union-attr]
    raw = "|".join(card.get(key, "") for key in ("title", "company", "location"))
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def collect(config: dict) -> tuple[list[Job], list[str]]:
    found: dict[str, Job] = {}
    errors: list[str] = []
    cap = int(config.get("max_results_per_search", 40))
    delay = float(config.get("request_delay_seconds", 1.5))
    filters = config.get("filters", {})
    locations = filter_location_values(config["locations"], filters)
    posted_days = filters.get("posted_within_days", config.get("max_job_age_days", 45))
    for query in config["searches"]:
        for location in locations:
            collected_here = 0
            for start in range(0, cap, 10):
                params_data = {"keywords": query, "location": location, "start": start}
                if posted_days is not None:
                    params_data["f_TPR"] = f"r{max(0, int(posted_days)) * 86400}"
                params = urlencode(params_data)
                url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + params
                try:
                    parser = CardParser()
                    parser.feed(fetch(url))
                    if not parser.jobs:
                        break
                    for card in parser.jobs:
                        if collected_here >= cap:
                            break
                        jid = job_id(card)
                        found[jid] = Job(
                            id=jid,
                            title=card.get("title", "").strip(),
                            company=card.get("company", "").strip(),
                            location=card.get("location", "").strip(),
                            url=normalize_url(card.get("url", "")),
                            posted=card.get("posted", "").strip(),
                            discovered_at=datetime.now(timezone.utc).isoformat(),
                        )
                        collected_here += 1
                except (HTTPError, URLError, TimeoutError) as exc:
                    errors.append(f"{query} / {location}: {exc}")
                    break
                time.sleep(delay)
    return list(found.values()), errors


def add_descriptions(jobs: list[Job], delay: float) -> list[str]:
    errors: list[str] = []
    for job in jobs:
        try:
            body = fetch(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job.id}")
            parser = TextParser()
            parser.feed(body)
            job.description = re.sub(r"\s+", " ", "".join(parser.parts)).strip()
        except (HTTPError, URLError, TimeoutError) as exc:
            errors.append(f"description {job.id}: {exc}")
        time.sleep(delay)
    return errors


def phrases(text: str) -> set[str]:
    lower = text.lower()
    tokens = set(re.findall(r"[a-z][a-z0-9+#.]{1,}", lower)) - STOP_WORDS
    return tokens | {term for term in SKILL_TERMS if term in lower}


def filter_blocked_companies(jobs: list[Job], blocked_companies: list[str]) -> list[Job]:
    """Remove blocked employers using normalized exact company-name matching."""
    blocked = {
        re.sub(r"[^a-z0-9]+", "", str(company).lower())
        for company in blocked_companies
        if str(company).strip()
    }
    return [
        job for job in jobs
        if re.sub(r"[^a-z0-9]+", "", job.company.lower()) not in blocked
    ]


def filter_excluded_seasons(jobs: list[Job], excluded_seasons: list[str]) -> list[Job]:
    parsed: list[tuple[str, str, str]] = []
    for value in excluded_seasons:
        text = str(value).strip().lower()
        season = re.search(r"\b(spring|summer|fall|autumn|winter)\b", text)
        year = re.search(r"\b(20\d{2})\b", text)
        if season and year:
            parsed.append((season.group(1), year.group(1), year.group(1)[-2:]))
    kept = []
    for job in jobs:
        title = job.title.lower()
        is_excluded = any(
            re.search(rf"\b{season}\b", title)
            and re.search(rf"(?:\b{year}\b|[’']?{short_year}\b)", title)
            for season, year, short_year in parsed
        )
        if not is_excluded:
            kept.append(job)
    return kept


def filter_internships(jobs: list[Job]) -> list[Job]:
    """Keep roles explicitly identified as internships or co-ops in the title."""
    pattern = re.compile(r"\b(?:intern(?:ship)?|co[\s-]?op)\b", re.IGNORECASE)
    return [job for job in jobs if pattern.search(job.title)]


def location_categories(value: str) -> tuple[set[str], bool]:
    """Return recognized countries plus whether a location is remote."""
    original = str(value or "")
    lower = original.lower()
    countries: set[str] = set()
    remote = bool(re.search(r"\b(remote|work from home|distributed)\b", lower))
    if any(marker in lower for marker in CANADA_MARKERS) or re.search(
        rf"(?:,\s*|\()({CANADA_PROVINCE_CODES})\b", original, re.IGNORECASE
    ):
        countries.add("canada")
    if any(marker in lower for marker in US_MARKERS) or re.search(r"\bU\.?S\.?A?\.?\b", original) or re.search(
        rf"(?:,\s*|\()({US_STATE_CODES})\b", original
    ):
        countries.add("united_states")
    return countries, remote


def location_allowed(value: str, filters: dict) -> bool:
    countries, remote = location_categories(value)
    enabled = filters.get("countries", {})
    canada = bool(enabled.get("canada", True))
    united_states = bool(enabled.get("united_states", True))
    if remote:
        if not filters.get("include_remote", True):
            return False
        if not countries:
            return True
    if countries:
        return ("canada" in countries and canada) or ("united_states" in countries and united_states)
    return bool(filters.get("include_unknown_locations", True))


def filter_location_values(values: list[str], filters: dict) -> list[str]:
    return [value for value in values if location_allowed(value, filters)]


def filter_job_locations(jobs: list[Job], filters: dict) -> list[Job]:
    return [job for job in jobs if location_allowed(job.location, filters)]


def parse_posted_datetime(value: str, now: datetime | None = None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    now = now or datetime.now(timezone.utc)
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    relative = re.search(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", raw, re.IGNORECASE)
    if not relative:
        return None
    amount = int(relative.group(1))
    unit = relative.group(2).lower()
    days = amount * {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30}[unit]
    return now - timedelta(days=days)


def filter_posted_dates(
    jobs: list[Job],
    posted_within_days: int | float | None,
    include_unknown: bool,
    now: datetime | None = None,
) -> list[Job]:
    if posted_within_days is None:
        return jobs
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(days=max(0, float(posted_within_days)))
    kept = []
    for job in jobs:
        posted = parse_posted_datetime(job.posted, now)
        if posted is None:
            if include_unknown:
                kept.append(job)
        elif posted >= cutoff:
            kept.append(job)
    return kept


def filter_title_keywords(jobs: list[Job], included: list[str], excluded: list[str]) -> list[Job]:
    include_terms = [str(term).strip().lower() for term in included if str(term).strip()]
    exclude_terms = [str(term).strip().lower() for term in excluded if str(term).strip()]
    return [
        job for job in jobs
        if (not include_terms or any(term in job.title.lower() for term in include_terms))
        and not any(term in job.title.lower() for term in exclude_terms)
    ]


def apply_config_filters(jobs: list[Job], config: dict, now: datetime | None = None) -> list[Job]:
    filters = config.get("filters", {})
    jobs = filter_blocked_companies(jobs, config.get("blocked_companies", []))
    target_season = config.get("goals", {}).get("target_season", "summer 2027")
    if filters.get("require_target_season_in_title", True):
        jobs = filter_target_season(jobs, target_season)
    if filters.get("exclude_mixed_seasons", True):
        jobs = filter_excluded_seasons(jobs, config.get("excluded_seasons", []))
    if filters.get("require_internship_in_title", config.get("goals", {}).get("must_be_internship", True)):
        jobs = filter_internships(jobs)
    jobs = filter_title_keywords(
        jobs,
        filters.get("include_title_keywords", []),
        filters.get("exclude_title_keywords", []),
    )
    jobs = filter_job_locations(jobs, filters)
    jobs = filter_posted_dates(
        jobs,
        filters.get("posted_within_days", config.get("max_job_age_days", 45)),
        bool(filters.get("include_unknown_posted_date", True)),
        now,
    )
    return jobs


def filter_target_season(jobs: list[Job], target_season: str) -> list[Job]:
    """Keep only jobs whose title explicitly names the requested season and year."""
    target = str(target_season).strip().lower()
    season_match = re.search(r"\b(spring|summer|fall|autumn|winter)\b", target)
    year_match = re.search(r"\b(20\d{2})\b", target)
    if not season_match or not year_match:
        return jobs
    season = season_match.group(1)
    year = year_match.group(1)
    short_year = year[-2:]
    patterns = (
        rf"\b{season}\b[^\n]{{0,24}}\b{year}\b",
        rf"\b{year}\b[^\n]{{0,24}}\b{season}\b",
        rf"\b{season}\b[^\n]{{0,24}}[’']?{short_year}\b",
        rf"[’']?{short_year}\b[^\n]{{0,24}}\b{season}\b",
    )
    return [job for job in jobs if any(re.search(pattern, job.title.lower()) for pattern in patterns)]


def score_jobs(jobs: list[Job], resume: str, goals: dict) -> None:
    resume_terms = phrases(resume)
    preferred = {str(x).lower() for x in goals.get("preferred_keywords", [])}
    targets = {str(x).lower() for x in goals.get("target_roles", [])}
    locations = {str(x).lower() for x in goals.get("preferred_locations", [])}
    avoid = {str(x).lower() for x in goals.get("avoid_keywords", [])}
    season = str(goals.get("target_season", "summer 2027")).lower()

    for job in jobs:
        title = job.title.lower()
        haystack = " ".join((job.title, job.company, job.location, job.description)).lower()
        job_terms = phrases(haystack)
        matched = sorted(resume_terms & job_terms)
        skill_matches = [term for term in matched if term in SKILL_TERMS or term in preferred]
        # Saturating overlap: 12 meaningful matches is approximately a full resume-fit score.
        overlap = 1 - math.exp(-len(matched) / 12)
        skill_bonus = min(len(skill_matches) / 8, 1)
        job.resume_fit = round(100 * (0.65 * overlap + 0.35 * skill_bonus), 1)

        goal_points = 0.0
        reasons: list[str] = []
        role_matches = [role for role in targets if all(part in title for part in role.split())]
        if role_matches:
            goal_points += 35
            reasons.append(f"target role: {role_matches[0]}")
        elif any(word in title for word in ("software", "developer", "product design", "design engineer", "ux", "ui")):
            goal_points += 20
        internship = any(word in haystack for word in ("intern", "internship", "co-op", "coop"))
        if internship:
            goal_points += 20
            reasons.append("internship/co-op")
        elif goals.get("must_be_internship"):
            goal_points -= 25
        season_parts = season.split()
        if all(part in haystack for part in season_parts):
            goal_points += 20
            reasons.append(season)
        elif "2027" in haystack:
            goal_points += 12
            reasons.append("mentions 2027")
        location_match = next((loc for loc in locations if loc in job.location.lower() or loc in haystack), None)
        if location_match:
            goal_points += 15
            reasons.append(f"preferred location: {location_match}")
        pref_matches = sorted(term for term in preferred if term in haystack)
        goal_points += min(len(pref_matches) * 3, 10)
        if pref_matches:
            reasons.append("goal keywords: " + ", ".join(pref_matches[:4]))
        penalties = sorted(term for term in avoid if term in haystack)
        goal_points -= min(len(penalties) * 20, 40)
        if penalties:
            reasons.append("penalty: " + ", ".join(penalties[:3]))
        job.goal_fit = round(max(0, min(100, goal_points)), 1)
        job.score = round(0.6 * job.resume_fit + 0.4 * job.goal_fit, 1)
        if skill_matches:
            reasons.insert(0, "resume matches: " + ", ".join(skill_matches[:6]))
        job.reasons = reasons or ["limited matching detail available"]


def load_previous(path: Path) -> dict[str, Job]:
    if not path.exists():
        return {}
    try:
        items = json.loads(path.read_text())
        return {item["id"]: Job(**item) for item in items}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def write_reports(
    jobs: list[Job],
    errors: list[str],
    output_dir: Path,
    state_path: Path | None = None,
    demo: bool = False,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_path or (ROOT / "state" / "jobs.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    jobs.sort(key=lambda item: item.score, reverse=True)
    payload = [asdict(job) for job in jobs]
    (output_dir / "jobs.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    generated = datetime.now().astimezone().strftime("%B %d, %Y at %I:%M %p %Z")

    def card(job: Job, rank: int | None = None) -> str:
        badge = f'<span class="rank">#{rank}</span>' if rank else ""
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in job.reasons)
        return f'''<article class="job">{badge}<div><h3><a href="{html.escape(job.url)}">{html.escape(job.title)}</a></h3>
        <p class="meta">{html.escape(job.company)} · {html.escape(job.location)} · {html.escape(job.posted or "date unavailable")} · {html.escape(job.source)}</p>
        <div class="scores"><b>{job.score:.0f} overall</b><span>{job.resume_fit:.0f} resume fit</span><span>{job.goal_fit:.0f} goal fit</span></div>
        <ul>{reasons}</ul></div></article>'''

    top = "".join(card(job, i) for i, job in enumerate(jobs[:10], 1)) or "<p>No matching jobs found today.</p>"
    rest = "".join(card(job) for job in jobs[10:])
    error_html = ""
    if errors:
        error_html = f'<details><summary>{len(errors)} collection warnings</summary><pre>{html.escape(chr(10).join(errors))}</pre></details>'
    report_label = "DEMO MATCH REPORT - NOT LIVE JOBS" if demo else "DAILY MATCH REPORT"
    document = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>Summer 2027 Job Matches</title><style>
    :root{{--ink:#17211b;--muted:#68726c;--paper:#f7f4ec;--card:#fff;--green:#1f6b4f;--line:#dfe3dd}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,sans-serif}}
    main{{max-width:980px;margin:auto;padding:48px 20px}}h1{{font-size:clamp(32px,6vw,64px);line-height:1;margin:0 0 10px;letter-spacing:-.04em}}
    h2{{margin-top:48px}}.intro,.meta{{color:var(--muted)}}.job{{position:relative;display:flex;gap:18px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;margin:14px 0;box-shadow:0 4px 18px #1d34250b}}
    .job>div{{min-width:0}}h3{{font-size:19px;margin:0}}a{{color:var(--green);text-decoration:none}}a:hover{{text-decoration:underline}}.rank{{font-size:24px;font-weight:800;color:var(--green);min-width:42px}}
    .scores{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}}.scores>*{{padding:4px 9px;border-radius:999px;background:#edf5f0;font-size:13px}}ul{{margin:8px 0 0;padding-left:20px}}details{{margin-top:30px}}pre{{white-space:pre-wrap}}
    </style></head><body><main><p class="intro">{report_label}</p><h1>Summer 2027 opportunities</h1>
    <p class="intro">Generated {html.escape(generated)} · {len(jobs)} unique jobs from LinkedIn and direct company boards · ranking = 60% resume fit + 40% goal fit</p>
    <h2>Your top 10</h2>{top}<h2>More matches</h2>{rest or '<p class="intro">The complete set is already in the top 10.</p>'}{error_html}
    </main></body></html>'''
    (output_dir / "report.html").write_text(document)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--resume", type=Path, default=ROOT / "profile" / "resume.txt")
    parser.add_argument("--output", type=Path, help="Report folder (defaults to output/, or output/demo for fixtures)")
    parser.add_argument("--company-boards", type=Path, default=ROOT / "company_boards.json")
    parser.add_argument("--skip-linkedin", action="store_true", help="Only collect direct company boards")
    parser.add_argument("--skip-company-boards", action="store_true", help="Only collect LinkedIn")
    parser.add_argument("--fixture", type=Path, help="Rank jobs from a JSON fixture without network access")
    args = parser.parse_args()
    if not args.config.exists() or not args.resume.exists():
        print("Setup required: copy config.example.json to config.json and profile/resume.example.txt to profile/resume.txt, then edit both.", file=sys.stderr)
        return 2
    config = json.loads(args.config.read_text())
    resume = args.resume.read_text(errors="replace")
    output_dir = args.output or (ROOT / "output" / "demo" if args.fixture else ROOT / "output")
    if args.fixture:
        jobs = []
        for item in json.loads(args.fixture.read_text()):
            fixture_job = Job(**item)
            fixture_job.source = "Demo fixture - not a live job"
            jobs.append(fixture_job)
        errors: list[str] = []
    else:
        jobs: list[Job] = []
        errors: list[str] = []
        if not args.skip_linkedin:
            linkedin_jobs, linkedin_errors = collect(config)
            jobs.extend(linkedin_jobs)
            errors.extend(linkedin_errors)
        if not args.skip_company_boards:
            if not args.company_boards.exists():
                errors.append(f"Company board configuration not found: {args.company_boards}")
            else:
                from company_boards import collect_company_boards

                boards = json.loads(args.company_boards.read_text())
                board_items, board_errors = collect_company_boards(boards)
                jobs.extend(Job(**item) for item in board_items)
                errors.extend(board_errors)
        jobs = list({job.id: job for job in jobs}.values())
        previous = load_previous(ROOT / "state" / "jobs.json")
        known_ids = {job.id for job in jobs}
        for jid, old in previous.items():
            if jid not in known_ids:
                jobs.append(old)
        jobs = apply_config_filters(jobs, config)
        detail_limit = int(config.get("max_descriptions_per_run", 80))
        missing_descriptions = [
            job for job in jobs if job.source == "LinkedIn" and not job.description
        ][:detail_limit]
        errors.extend(add_descriptions(missing_descriptions, float(config.get("request_delay_seconds", 1.5))))
    score_jobs(jobs, resume, config["goals"])
    if not args.fixture:
        filters = config.get("filters", {})
        minimum_score = float(filters.get("minimum_match_score", 0))
        jobs = [job for job in jobs if job.score >= minimum_score]
        jobs.sort(key=lambda item: item.score, reverse=True)
        max_jobs = filters.get("max_jobs_in_report")
        if max_jobs is not None:
            jobs = jobs[:max(0, int(max_jobs))]
    state_path = output_dir / "fixture-state.json" if args.fixture else None
    write_reports(jobs, errors, output_dir, state_path=state_path, demo=bool(args.fixture))
    print(f"Wrote {len(jobs)} ranked jobs to {output_dir / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
