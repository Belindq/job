#!/usr/bin/env python3
"""Build and email the latest Summer 2027 report using config/email.env."""

from __future__ import annotations

import json
import smtplib
import ssl
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
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "config" / "email.env"
JOBS_PATH = ROOT / "output" / "jobs.json"
PDF_PATH = ROOT / "output" / "pdf" / "job-report.pdf"


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


def build_pdf(jobs: list[dict], path: Path, generated: datetime | None = None) -> None:
    """Create a polished PDF with clickable title and application links."""
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = generated or datetime.now().astimezone()
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
    meta_style = ParagraphStyle(
        "Meta", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5,
        leading=11, textColor=muted, spaceAfter=4,
    )
    reason_style = ParagraphStyle(
        "Reason", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5,
        leading=11, textColor=ink, leftIndent=8,
    )
    link_style = ParagraphStyle(
        "ApplyLink", parent=styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=8.5, leading=11, textColor=green,
    )

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(0.65 * inch, 0.47 * inch, 7.85 * inch, 0.47 * inch)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(0.65 * inch, 0.30 * inch, "Summer 2027 internship matches")
        canvas.drawRightString(7.85 * inch, 0.30 * inch, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(path), pagesize=letter, rightMargin=0.65 * inch, leftMargin=0.65 * inch,
        topMargin=0.55 * inch, bottomMargin=0.62 * inch,
        title="Summer 2027 Internship Matches", author="Job Hunter",
    )
    story = [
        Paragraph("Summer 2027 opportunities", title_style),
        Paragraph(
            f"Generated {escape(generated.strftime('%B %d, %Y at %I:%M %p %Z'))}"
            f" &nbsp;&bull;&nbsp; {len(jobs)} explicit-season matches"
            " &nbsp;&bull;&nbsp; Ranked for resume and goal fit",
            intro_style,
        ),
    ]
    if not jobs:
        story.append(Paragraph("No open Summer 2027 matches were found in this run.", meta_style))
    for index, job in enumerate(jobs, 1):
        url = valid_url(job.get("url"))
        title = escape(str(job.get("title") or "Untitled job"))
        title_markup = f'<link href={quoteattr(url)} color="#1F6B4F">{index}. {title}</link>' if url else f"{index}. {title}"
        meta = " | ".join(
            escape(str(value)) for value in (
                job.get("company") or "Unknown company",
                job.get("location") or "Location unavailable",
                f"Score {float(job.get('score', 0)):.0f}",
            )
        )
        reasons = job.get("reasons") or []
        block = [Paragraph(title_markup, job_title_style), Paragraph(meta, meta_style)]
        if reasons:
            block.append(Paragraph("Match: " + escape("; ".join(str(reason) for reason in reasons[:3])), reason_style))
        if url:
            block.append(Paragraph(f'<link href={quoteattr(url)} color="#1F6B4F">Open actual job posting</link>', link_style))
        block.append(Spacer(1, 10))
        story.append(KeepTogether(block))
    document.build(story, onFirstPage=footer, onLaterPages=footer)


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
    settings = load_env(ENV_PATH)
    required = {"SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_TO"}
    missing = required - settings.keys()
    if missing:
        raise SystemExit(f"Missing email settings: {', '.join(sorted(missing))}")
    if not JOBS_PATH.exists():
        raise SystemExit(f"Job data not found: {JOBS_PATH}")
    jobs = json.loads(JOBS_PATH.read_text())
    generated = datetime.now().astimezone()
    build_pdf(jobs, PDF_PATH, generated)
    send_report(settings, PDF_PATH, len(jobs), generated)
    print(f"Emailed {len(jobs)} jobs with PDF: {PDF_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
