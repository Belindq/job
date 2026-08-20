"""Collectors for public company-owned job boards and common ATS feeds."""

from __future__ import annotations

import hashlib
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)
INTERN_RE = re.compile(r"\b(intern(?:ship)?|co[ -]?op|university trainee)\b", re.I)


def request_text(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def request_json(url: str) -> Any:
    return json.loads(request_text(url))


def plain(value: Any) -> str:
    if value is None:
        return ""
    parser = _VisibleTextParser()
    parser.feed(html.unescape(str(value)))
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def is_internship(title: str, description: str = "") -> bool:
    # Description-only matches create bad false positives (for example, a
    # recruiting manager whose description says they oversee interns).
    return bool(INTERN_RE.search(title))


def stable_id(company: str, external_id: Any, url: str) -> str:
    value = str(external_id or "").strip()
    if not value:
        value = hashlib.sha1(url.encode()).hexdigest()[:16]
    company_key = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    return f"board:{company_key}:{value}"


def make_job(company: str, external_id: Any, title: str, location: str, url: str,
             description: str = "", posted: str = "", source: str = "Company board") -> dict[str, Any]:
    return {
        "id": stable_id(company, external_id, url),
        "title": plain(title),
        "company": company,
        "location": plain(location) or "Location not specified",
        "url": html.unescape(url),
        "posted": posted or "",
        "description": plain(description),
        "source": source,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg"}:
            self.hidden += 1
        if tag in {"p", "li", "br", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


class _StructuredDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture = False
        self.buffer: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and "ld+json" in (values.get("type") or "").lower():
            self.capture = True
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.capture:
            self.scripts.append("".join(self.buffer))
            self.capture = False


class _InternLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.href = ""
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href") or ""
            self.text = []

    def handle_data(self, data: str) -> None:
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href:
            label = re.sub(r"\s+", " ", "".join(self.text)).strip()
            job_url = urljoin(self.base_url, self.href)
            job_path = job_url.lower()
            looks_like_job = any(part in job_path for part in ("/job/", "/jobs/", "/position/", "/positions/", "requisition"))
            if is_internship(label) and len(label) > 5 and looks_like_job:
                self.links.append((label, job_url))
            self.href = ""
            self.text = []


def collect_greenhouse(board: dict[str, Any]) -> list[dict[str, Any]]:
    company, token = board["company"], board["token"]
    data = request_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    jobs = []
    for item in data.get("jobs", []):
        title, description = item.get("title", ""), item.get("content", "")
        if not is_internship(title, plain(description)):
            continue
        jobs.append(make_job(
            company, item.get("id"), title, (item.get("location") or {}).get("name", ""),
            item.get("absolute_url", ""), description, item.get("updated_at", ""), "Company board · Greenhouse",
        ))
    return jobs


def collect_ashby(board: dict[str, Any]) -> list[dict[str, Any]]:
    company, token = board["company"], board["token"]
    data = request_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    jobs = []
    for item in data.get("jobs", []):
        title = item.get("title", "")
        description = item.get("descriptionHtml") or item.get("descriptionPlain") or ""
        if not is_internship(title, plain(description)):
            continue
        extra = item.get("secondaryLocations") or []
        locations = [item.get("location", "")] + [loc.get("location", "") for loc in extra if isinstance(loc, dict)]
        jobs.append(make_job(
            company, item.get("id"), title, " / ".join(filter(None, locations)),
            item.get("jobUrl") or item.get("applyUrl") or "", description,
            item.get("publishedAt", ""), "Company board · Ashby",
        ))
    return jobs


def collect_lever(board: dict[str, Any]) -> list[dict[str, Any]]:
    company, token = board["company"], board["token"]
    data = request_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    jobs = []
    for item in data if isinstance(data, list) else []:
        title = item.get("text", "")
        description = " ".join(filter(None, [item.get("descriptionPlain"), item.get("additionalPlain")]))
        if not is_internship(title, description):
            continue
        created = item.get("createdAt")
        posted = datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if isinstance(created, (int, float)) else ""
        jobs.append(make_job(
            company, item.get("id"), title, (item.get("categories") or {}).get("location", ""),
            item.get("hostedUrl") or item.get("applyUrl") or "", description, posted, "Company board · Lever",
        ))
    return jobs


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _jsonld_location(value: Any) -> str:
    locations: list[str] = []
    for item in value if isinstance(value, list) else [value]:
        if not isinstance(item, dict):
            continue
        address = item.get("address", item)
        if isinstance(address, dict):
            parts = [address.get(key, "") for key in ("addressLocality", "addressRegion", "addressCountry")]
            locations.append(", ".join(str(part) for part in parts if part))
    return " / ".join(filter(None, locations))


def collect_generic(board: dict[str, Any]) -> list[dict[str, Any]]:
    company, url = board["company"], board["url"]
    body = request_text(url)
    structured = _StructuredDataParser()
    structured.feed(body)
    jobs: list[dict[str, Any]] = []
    for script in structured.scripts:
        try:
            data = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in _walk_json(data):
            item_type = item.get("@type", "")
            is_job_posting = item_type == "JobPosting" or (
                isinstance(item_type, list) and "JobPosting" in item_type
            )
            if not is_job_posting:
                continue
            title, description = item.get("title", ""), item.get("description", "")
            if not is_internship(title, plain(description)):
                continue
            identifier = item.get("identifier", "")
            if isinstance(identifier, dict):
                identifier = identifier.get("value", "")
            jobs.append(make_job(
                company, identifier, title, _jsonld_location(item.get("jobLocation", [])),
                item.get("url") or url, description, item.get("datePosted", ""), "Company board",
            ))
    if jobs:
        return jobs
    links = _InternLinkParser(url)
    links.feed(body)
    seen: set[str] = set()
    for title, job_url in links.links:
        if job_url in seen:
            continue
        seen.add(job_url)
        jobs.append(make_job(company, "", title, "", job_url, source="Company board"))
    return jobs


def collect_riot(board: dict[str, Any]) -> list[dict[str, Any]]:
    company, url = board["company"], board["url"]
    decoded = html.unescape(request_text(url))
    decoder = json.JSONDecoder()
    jobs = []
    seen: set[str] = set()
    for match in re.finditer(r'\{"title":', decoded):
        try:
            item, _ = decoder.raw_decode(decoded[match.start():])
        except json.JSONDecodeError:
            continue
        path = item.get("url", "") if isinstance(item, dict) else ""
        title = item.get("title", "") if isinstance(item, dict) else ""
        if not path.startswith("/j/") or path in seen or not is_internship(title):
            continue
        seen.add(path)
        location = item.get("officeName", "")
        extras = item.get("additionalOfficeNames", [])
        if extras:
            location = " / ".join([location] + extras)
        jobs.append(make_job(company, path.rsplit("/", 1)[-1], title, location,
                             urljoin("https://www.riotgames.com/en/", path.lstrip("/")),
                             source="Company board · Riot Games"))
    return jobs


COLLECTORS = {
    "greenhouse": collect_greenhouse,
    "ashby": collect_ashby,
    "lever": collect_lever,
    "riot": collect_riot,
    "generic": collect_generic,
}


def collect_company_boards(boards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    jobs: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    def run(board: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        collector = COLLECTORS[board.get("collector", "generic")]
        return board, collector(board)

    # Boards are on independent company domains. A small pool keeps a 50-board
    # sweep quick without creating a burst against any single service.
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(boards)))) as pool:
        futures = {pool.submit(run, board): board for board in boards}
        for future in as_completed(futures):
            board = futures[future]
            company = board.get("company", "Unknown company")
            try:
                _, collected = future.result()
                for job in collected:
                    jobs[job["id"]] = job
            except (KeyError, HTTPError, URLError, TimeoutError, ValueError, TypeError, OSError) as exc:
                errors.append(f"{company} company board: {exc}")
    return list(jobs.values()), errors
