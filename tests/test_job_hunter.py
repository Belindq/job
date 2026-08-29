import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("job_hunter", ROOT / "src" / "job_hunter.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
import sys
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

BOARD_SPEC = importlib.util.spec_from_file_location("company_boards", ROOT / "src" / "company_boards.py")
BOARDS = importlib.util.module_from_spec(BOARD_SPEC)
assert BOARD_SPEC and BOARD_SPEC.loader
sys.modules[BOARD_SPEC.name] = BOARDS
BOARD_SPEC.loader.exec_module(BOARDS)


class RankingTests(unittest.TestCase):
    def test_target_internship_ranks_above_unrelated_senior_role(self):
        config = json.loads((ROOT / "config.example.json").read_text())
        data = json.loads((ROOT / "tests" / "fixtures" / "jobs.json").read_text())
        jobs = [MODULE.Job(**item) for item in data]
        resume = "React TypeScript Python Figma frontend design systems product design"
        MODULE.score_jobs(jobs, resume, config["goals"])
        jobs.sort(key=lambda item: item.score, reverse=True)
        self.assertEqual(jobs[0].id, "1")
        self.assertGreater(jobs[0].score, jobs[1].score)

    def test_blocked_company_is_removed_from_all_sources(self):
        jobs = [
            MODULE.Job(id="p1", title="Intern", company="Palantir", location="NY", url="https://example.com/p1"),
            MODULE.Job(id="n1", title="Intern", company="Notion", location="NY", url="https://example.com/n1"),
        ]
        kept = MODULE.filter_blocked_companies(jobs, ["Palantir"])
        self.assertEqual([job.company for job in kept], ["Notion"])

    def test_only_explicit_target_season_is_kept(self):
        jobs = [
            MODULE.Job(id="s", title="Software Engineer Intern - Summer 2027", company="A", location="NY", url="https://example.com/s"),
            MODULE.Job(id="w", title="Software Engineer Intern (Winter 2027)", company="B", location="NY", url="https://example.com/w"),
            MODULE.Job(id="a", title="2027 Software Engineering Intern", company="C", location="NY", url="https://example.com/a"),
            MODULE.Job(id="r", title="2027 Summer Product Design Intern", company="D", location="NY", url="https://example.com/r"),
        ]
        kept = MODULE.filter_target_season(jobs, "summer 2027")
        self.assertEqual([job.id for job in kept], ["s", "r"])

    def test_excluded_winter_season_is_removed(self):
        jobs = [
            MODULE.Job(id="summer", title="Engineering Intern - Summer 2027", company="Co", location="Toronto", url="https://example.com/summer"),
            MODULE.Job(id="winter", title="Engineering Intern - Winter 2027", company="Co", location="Toronto", url="https://example.com/winter"),
        ]
        kept = MODULE.filter_excluded_seasons(jobs, ["winter 2027"])
        self.assertEqual([job.id for job in kept], ["summer"])

    def test_mixed_summer_fall_title_is_removed(self):
        jobs = [
            MODULE.Job(id="summer", title="Engineering Intern - Summer 2027", company="A", location="NY", url="https://example.com/s"),
            MODULE.Job(id="mixed", title="Engineering Co-op (Summer/Fall 2027)", company="B", location="NY", url="https://example.com/m"),
            MODULE.Job(id="short", title="RF Modules Summer/Fall Co-Op (June-Dec '27)", company="C", location="NY", url="https://example.com/short"),
        ]
        kept = MODULE.filter_excluded_seasons(jobs, ["fall 2027"])
        self.assertEqual([job.id for job in kept], ["summer"])

    def test_non_intern_summer_roles_are_removed(self):
        jobs = [
            MODULE.Job(id="intern", title="Software Engineer Intern - Summer 2027", company="A", location="NY", url="https://example.com/i"),
            MODULE.Job(id="coop", title="Design Engineering Co-op Summer 2027", company="B", location="NY", url="https://example.com/c"),
            MODULE.Job(id="grad", title="Software Engineer New Grad Summer 2027", company="C", location="NY", url="https://example.com/g"),
        ]
        kept = MODULE.filter_internships(jobs)
        self.assertEqual([job.id for job in kept], ["intern", "coop"])

    def test_country_and_remote_toggles(self):
        jobs = [
            MODULE.Job(id="ca", title="Intern", company="A", location="Toronto, ON", url="https://example.com/ca"),
            MODULE.Job(id="us", title="Intern", company="B", location="Seattle, WA", url="https://example.com/us"),
            MODULE.Job(id="uk", title="Intern", company="C", location="London, UK", url="https://example.com/uk"),
            MODULE.Job(id="remote", title="Intern", company="D", location="Remote", url="https://example.com/r"),
        ]
        filters = {
            "countries": {"canada": False, "united_states": True},
            "include_remote": True,
            "include_unknown_locations": False,
        }
        kept = MODULE.filter_job_locations(jobs, filters)
        self.assertEqual([job.id for job in kept], ["us", "remote"])

    def test_posted_date_and_unknown_date_toggles(self):
        now = datetime(2026, 8, 28, tzinfo=timezone.utc)
        jobs = [
            MODULE.Job(id="new", title="Intern", company="A", location="NY", url="https://example.com/n", posted="2026-08-20"),
            MODULE.Job(id="old", title="Intern", company="B", location="NY", url="https://example.com/o", posted="2026-06-01"),
            MODULE.Job(id="unknown", title="Intern", company="C", location="NY", url="https://example.com/u"),
        ]
        strict = MODULE.filter_posted_dates(jobs, 30, False, now)
        permissive = MODULE.filter_posted_dates(jobs, 30, True, now)
        self.assertEqual([job.id for job in strict], ["new"])
        self.assertEqual([job.id for job in permissive], ["new", "unknown"])

    def test_title_keyword_filters(self):
        jobs = [
            MODULE.Job(id="se", title="Software Engineering Intern", company="A", location="NY", url="https://example.com/se"),
            MODULE.Job(id="me", title="Mechanical Engineering Intern", company="B", location="NY", url="https://example.com/me"),
            MODULE.Job(id="phd", title="Software Engineering Intern - PhD", company="C", location="NY", url="https://example.com/phd"),
        ]
        kept = MODULE.filter_title_keywords(jobs, ["software"], ["phd"])
        self.assertEqual([job.id for job in kept], ["se"])

    def test_report_is_written(self):
        job = MODULE.Job(id="1", title="Intern", company="Co", location="Toronto", url="https://example.com", score=80)
        with tempfile.TemporaryDirectory() as folder:
            MODULE.write_reports([job], [], Path(folder), Path(folder) / "state.json")
            self.assertIn("Your top 10", (Path(folder) / "report.html").read_text())

    def test_company_list_has_50_and_priority_companies(self):
        boards = json.loads((ROOT / "company_boards.json").read_text())
        self.assertEqual(len(boards), 50)
        names = {board["company"] for board in boards}
        self.assertTrue({"Figma", "Notion", "Riot Games", "Roblox", "Google", "Meta", "Amazon", "Apple", "Netflix"} <= names)

    def test_greenhouse_collector_keeps_only_internships(self):
        original = BOARDS.request_json
        BOARDS.request_json = lambda _: {"jobs": [
            {"id": 7, "title": "Product Design Intern", "location": {"name": "New York"},
             "absolute_url": "https://example.com/7", "content": "Use Figma", "updated_at": "2026-08-01"},
            {"id": 8, "title": "Senior Designer", "location": {"name": "New York"},
             "absolute_url": "https://example.com/8", "content": "Lead the team"},
        ]}
        try:
            jobs = BOARDS.collect_greenhouse({"company": "Figma", "token": "figma"})
        finally:
            BOARDS.request_json = original
        self.assertEqual([job["title"] for job in jobs], ["Product Design Intern"])
        self.assertEqual(jobs[0]["source"], "Company board · Greenhouse")

    def test_generic_collector_reads_jobposting_jsonld(self):
        markup = '''<script type="application/ld+json">{
          "@type":"JobPosting", "title":"Software Engineer Intern",
          "description":"Build products with Python", "datePosted":"2026-08-01",
          "url":"https://example.com/jobs/1", "identifier":{"value":"one"},
          "jobLocation":{"address":{"addressLocality":"Toronto","addressCountry":"Canada"}}
        }</script>'''
        original = BOARDS.request_text
        BOARDS.request_text = lambda _: markup
        try:
            jobs = BOARDS.collect_generic({"company": "Example", "url": "https://example.com/jobs"})
        finally:
            BOARDS.request_text = original
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "Toronto, Canada")


if __name__ == "__main__":
    unittest.main()
