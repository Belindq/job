import importlib.util
import json
import tempfile
import unittest
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
