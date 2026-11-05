import importlib.util
import os
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def load_summaries_module():
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    with patch("boto3.Session") as mock_session:
        mock_session.return_value.resource.return_value = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "post_daily_summaries_under_test",
            os.path.join(REPO_ROOT, "scripts", "23_post_daily_summaries.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


summaries = load_summaries_module()


def summary_html(date_text):
    return f"<span class='highlight'>MILWAUKEE</span> <span class='updated'>({date_text})</span> — The Brewers won."


class ParseSummaryDateTest(unittest.TestCase):
    def test_game_date(self):
        self.assertEqual(
            summaries.parse_summary_date(summary_html("November 2"), date(2026, 11, 5)),
            date(2026, 11, 2),
        )

    def test_last_season_game_read_in_january(self):
        self.assertEqual(
            summaries.parse_summary_date(summary_html("November 2"), date(2027, 1, 10)),
            date(2026, 11, 2),
        )

    def test_off_season_format(self):
        self.assertIsNone(summaries.parse_summary_date(summary_html("February 2027"), date(2027, 2, 10)))

    def test_no_date(self):
        self.assertIsNone(summaries.parse_summary_date("No summary available.", date(2026, 11, 5)))
        self.assertIsNone(summaries.parse_summary_date(summary_html("Smarch 2"), date(2026, 11, 5)))


class StaleReportTest(unittest.TestCase):
    def run_main(self, summary_type, date_text, today):
        data = [{"stat": "summary", "value": summary_html(date_text)}, {"stat": "era", "value": "3.10"}]
        fake_now = MagicMock()
        fake_now.date.return_value = today
        fake_now.strftime.return_value = today.isoformat()
        with patch.object(sys, "argv", ["prog", "--type", summary_type]), \
             patch.object(summaries, "datetime", wraps=summaries.datetime) as mock_datetime, \
             patch.object(summaries, "get_last_post_date", return_value=None), \
             patch.object(summaries.requests, "get") as mock_get, \
             patch.object(summaries, "post_to_bluesky") as mock_post:
            mock_datetime.now.return_value = fake_now
            mock_get.return_value.json.return_value = data
            summaries.main()
        return mock_post

    def test_skips_report_in_off_season(self):
        self.run_main("pitching", "November 2", date(2026, 11, 8)).assert_not_called()

    def test_posts_report_after_off_day(self):
        self.run_main("pitching", "July 13", date(2026, 7, 17)).assert_called_once()


if __name__ == "__main__":
    unittest.main()
