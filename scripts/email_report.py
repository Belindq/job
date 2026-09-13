#!/usr/bin/env python3
"""Build and email the latest Summer 2027 report using config/email.env."""

from __future__ import annotations

import json
import smtplib
import ssl
import argparse
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "config" / "email.env"
JOBS_PATH = ROOT / "output" / "jobs.json"
PDF_PATH = ROOT / "output" / "pdf" / "job-report.pdf"
SENT_STATE_PATH = ROOT / "state" / "email-sent.json"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def valid_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def job_key(job: dict) -> str:
    """Return a stable per-posting key for delivery history."""
    return str(job.get("id") or valid_url(job.get("url")) or "|".join(
        str(job.get(field) or "").strip().lower() for field in ("company", "title", "location")
    ))


def load_sent_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    values = payload.get("sent_job_keys", []) if isinstance(payload, dict) else payload
    return {str(value) for value in values}


def save_sent_keys(path: Path, keys: set[str], sent_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "last_successful_email": sent_at.isoformat(),
        "sent_job_keys": sorted(keys),
    }, indent=2))


def new_jobs_first(jobs: list[dict], sent_keys: set[str]) -> list[dict]:
    """Move unseen jobs first while preserving ranking within each group."""
    return sorted(jobs, key=lambda job: job_key(job) in sent_keys)


def build_pdf(
    jobs: list[dict],
    path: Path,
    generated: datetime | None = None,
    sent_keys: set[str] | None = None,
    profile_name: str = "",
) -> tuple[int, int]:
    """Create a polished PDF with clickable title and application links."""
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = generated or datetime.now().astimezone()
    sent_keys = sent_keys or set()
    new_count = sum(job_key(job) not in sent_keys for job in jobs)
    previous_count = len(jobs) - new_count
    ordered_jobs = new_jobs_first(jobs, sent_keys)
    styles = getSampleStyleSheet()
    ink = colors.HexColor("#17211B")
    green = colors.HexColor("#1F6B4F")
    muted = colors.HexColor("#68726C")
    line = colors.HexColor("#DDE5DF")
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=27, leading=30, textColor=ink, alignment=TA_CENTER, spaceAfter=8,
    )
    intro_style = ParagraphStyle(
        "Intro", parent=styles["BodyText"], fontName="Helvetica", fontSize=9,
        leading=13, textColor=muted, alignment=TA_CENTER, spaceAfter=18,
    )
    job_title_style = ParagraphStyle(
        "JobTitle", parent=styles["Heading3"], fontName="Helvetica-Bold",
        fontSize=11.5, leading=14, textColor=green, spaceAfter=4,
    )
    status_style = ParagraphStyle(
        "DeliveryStatus", parent=styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=7.5, leading=9, textColor=green,
    )
    meta_style = ParagraphStyle(
        "Meta", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5,
        leading=11, textColor=muted, spaceAfter=4,
    )
    reason_style = ParagraphStyle(
        "Reason", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5,
        leading=11, textColor=ink, leftIndent=8,
    )

    page_width, page_height = letter
    left = 0.65 * inch
    right = 0.65 * inch
    top = 0.55 * inch
    bottom = 0.62 * inch
    content_width = page_width - left - right
    pdf = pdfcanvas.Canvas(str(path), pagesize=letter)
    pdf.setTitle("Summer 2027 Internship Matches")
    pdf.setAuthor("Job Hunter")
    page_number = 1
    y = page_height - top

    def footer() -> None:
        pdf.saveState()
        pdf.setStrokeColor(line)
        pdf.line(left, 0.47 * inch, page_width - right, 0.47 * inch)
        pdf.setFont("Helvetica", 7.5)
        pdf.setFillColor(muted)
        pdf.drawString(left, 0.30 * inch, "Summer 2027 internship matches")
        pdf.drawRightString(page_width - right, 0.30 * inch, f"Page {page_number}")
        pdf.restoreState()

    def draw_paragraph(paragraph: Paragraph, gap: float = 0) -> None:
        nonlocal y
        _, height = paragraph.wrap(content_width, page_height)
        paragraph.drawOn(pdf, left, y - height)
        y -= height + gap

    def start_new_page() -> None:
        nonlocal y, page_number
        footer()
        pdf.showPage()
        page_number += 1
        y = page_height - top

    draw_paragraph(Paragraph(
        "Summer 2027 opportunities" + (f" for {escape(profile_name.title())}" if profile_name else ""),
        title_style,
    ), 8)
    draw_paragraph(Paragraph(
        f"Generated {escape(generated.strftime('%B %d, %Y at %I:%M %p %Z'))}"
        f" &nbsp;&bull;&nbsp; {len(jobs)} explicit-season matches"
        f" &nbsp;&bull;&nbsp; {new_count} new / {previous_count} previously sent"
        " &nbsp;&bull;&nbsp; Ranked for resume and goal fit",
        intro_style,
    ), 18)
    if not jobs:
        draw_paragraph(Paragraph("No open Summer 2027 matches were found in this run.", meta_style))
    for index, job in enumerate(ordered_jobs, 1):
        url = valid_url(job.get("url"))
        is_new = job_key(job) not in sent_keys
        status = "NEW" if is_new else "PREVIOUSLY SENT"
        title = escape(str(job.get("title") or "Untitled job"))
        title_markup = f'<link href={quoteattr(url)} color="#1F6B4F">{index}. {title}</link>' if url else f"{index}. {title}"
        meta = " | ".join(
            escape(str(value)) for value in (
                job.get("company") or "Unknown company",
                job.get("location") or "Location unavailable",
                f"Score {float(job.get('score', 0)):.0f}",
            )
        )
        if url:
            meta += f' | <link href={quoteattr(url)} color="#1F6B4F"><b>Open actual job posting</b></link>'
        reasons = job.get("reasons") or []
        status_color = "#1F6B4F" if is_new else "#68726C"
        block: list[tuple[Paragraph, float]] = [
            (Paragraph(f'<font color="{status_color}">{status}</font>', status_style), 2),
            (Paragraph(title_markup, job_title_style), 4),
            (Paragraph(meta, meta_style), 4),
        ]
        if reasons:
            block.append((Paragraph("Match: " + escape("; ".join(str(reason) for reason in reasons[:3])), reason_style), 0))
        total_height = 10 + sum(paragraph.wrap(content_width, page_height)[1] + gap for paragraph, gap in block)
        if y - total_height < bottom:
            start_new_page()
        for paragraph, gap in block:
            draw_paragraph(paragraph, gap)
        y -= 10
    footer()
    pdf.save()
    return new_count, previous_count


def send_report(
    settings: dict[str, str],
    pdf_path: Path,
    job_count: int,
    generated: datetime,
    subject_prefix: str = "",
) -> None:
    message = EmailMessage()
    message["From"] = settings["SMTP_USERNAME"]
    message["To"] = settings["EMAIL_TO"]
    message["Subject"] = f"{subject_prefix}Summer 2027 internship matches - {generated.strftime('%b %d, %Y')}"
    message.set_content(
        f"Attached are {job_count} Summer 2027 internship matches. "
        "Every job title and 'Open actual job posting' label is clickable."
    )
    message.add_attachment(
        pdf_path.read_bytes(), maintype="application", subtype="pdf", filename="summer-2027-job-report.pdf"
    )
    with smtplib.SMTP(settings["SMTP_HOST"], int(settings["SMTP_PORT"]), timeout=30) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(settings["SMTP_USERNAME"], settings["SMTP_PASSWORD"])
        server.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=ENV_PATH)
    parser.add_argument("--jobs", type=Path, default=JOBS_PATH)
    parser.add_argument("--pdf", type=Path, default=PDF_PATH)
    parser.add_argument("--sent-state", type=Path, default=SENT_STATE_PATH)
    parser.add_argument("--profile-name", default="")
    args = parser.parse_args()
    settings = load_env(args.env)
    required = {"SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_TO"}
    missing = required - settings.keys()
    if missing:
        raise SystemExit(f"Missing email settings: {', '.join(sorted(missing))}")
    if not args.jobs.exists():
        raise SystemExit(f"Job data not found: {args.jobs}")
    jobs = json.loads(args.jobs.read_text())
    generated = datetime.now().astimezone()
    sent_keys = load_sent_keys(args.sent_state)
    new_count, previous_count = build_pdf(jobs, args.pdf, generated, sent_keys, args.profile_name)
    prefix = f"{args.profile_name}: " if args.profile_name else ""
    send_report(settings, args.pdf, len(jobs), generated, subject_prefix=prefix)
    save_sent_keys(args.sent_state, sent_keys | {job_key(job) for job in jobs}, generated)
    print(f"Emailed {len(jobs)} jobs ({new_count} new, {previous_count} previously sent) with PDF: {args.pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
