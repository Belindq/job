import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "email_report.py"
SPEC = importlib.util.spec_from_file_location("email_report", MODULE_PATH)
email_report = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(email_report)


class EmailReportTests(unittest.TestCase):
    def test_new_jobs_are_moved_before_previously_sent_jobs(self):
        jobs = [
            {"id": "sent-high-score", "score": 95},
            {"id": "new-high-score", "score": 90},
            {"id": "sent-low-score", "score": 80},
            {"id": "new-low-score", "score": 70},
        ]
        ordered = email_report.new_jobs_first(
            jobs, {"sent-high-score", "sent-low-score"}
        )
        self.assertEqual(
            [job["id"] for job in ordered],
            ["new-high-score", "new-low-score", "sent-high-score", "sent-low-score"],
        )

    def test_sent_history_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sent.json"
            sent_at = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
            email_report.save_sent_keys(path, {"job-1", "job-2"}, sent_at)
            self.assertEqual(email_report.load_sent_keys(path), {"job-1", "job-2"})

    def test_pdf_counts_new_and_previously_sent_jobs(self):
        jobs = [
            {
                "id": "job-1",
                "title": "Summer 2027 Software Engineering Intern",
                "company": "Example",
                "location": "Toronto, Canada",
                "url": "https://example.com/jobs/1",
                "score": 91,
                "reasons": ["Strong Python match"],
            },
            {
                "id": "job-2",
                "title": "Summer 2027 Product Design Intern",
                "company": "Example",
                "location": "Remote",
                "url": "https://example.com/jobs/2",
                "score": 85,
                "reasons": ["Product design goal"],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            counts = email_report.build_pdf(
                jobs,
                path,
                datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc),
                {"job-2"},
                "friend",
            )
            self.assertEqual(counts, (1, 1))
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
