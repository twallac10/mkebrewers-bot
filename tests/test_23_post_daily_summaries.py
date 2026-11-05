import importlib.util
import os
import sys
import unittest
from datetime import date, datetime
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


def schedule(*completed_dates, upcoming=()):
    rows = [{"date": d, "opp_name": "Tampa Bay Rays", "placement": "last"} for d in completed_dates]
    return rows + [{"date": d, "opp_name": "Chicago Cubs", "placement": "next"} for d in upcoming]


class GetLastGameDateTest(unittest.TestCase):
    def test_most_recent_completed_game(self):
        rows = schedule("Oct 27", "Oct 28", upcoming=["Oct 30"])
        self.assertEqual(summaries.get_last_game_date(rows, date(2026, 11, 5)), date(2026, 10, 28))

    def test_last_season_game_read_in_january(self):
        self.assertEqual(summaries.get_last_game_date(schedule("Oct 28"), date(2027, 1, 10)), date(2026, 10, 28))

    def test_leap_day_read_the_next_year(self):
        self.assertEqual(summaries.get_last_game_date(schedule("Feb 29"), date(2029, 1, 10)), date(2028, 2, 29))
        self.assertEqual(summaries.get_last_game_date(schedule("Feb 29"), date(2028, 3, 2)), date(2028, 2, 29))

    def test_no_completed_games(self):
        self.assertIsNone(summaries.get_last_game_date(schedule(upcoming=["Mar 26"]), date(2027, 3, 1)))
        self.assertIsNone(summaries.get_last_game_date([], date(2027, 3, 1)))

    def test_malformed_date(self):
        self.assertIsNone(summaries.get_last_game_date([{"placement": "last"}], date(2026, 11, 5)))
        self.assertIsNone(summaries.get_last_game_date(schedule("Smarch 2"), date(2026, 11, 5)))


class StaleReportTest(unittest.TestCase):
    def run_main(self, summary_type, schedule_rows, today):
        # Real summaries carry the date the data was refreshed, not the last game date
        summary_data = [
            {"stat": "summary", "value": summary_html(today.strftime("%B %-d"))},
            {"stat": "era", "value": "3.10"},
        ]

        def fake_get(url, **kwargs):
            response = MagicMock()
            response.json.return_value = schedule_rows if "schedule" in url else summary_data
            return response

        fake_now = MagicMock()
        fake_now.date.return_value = today
        fake_now.strftime.return_value = today.isoformat()
        with patch.object(sys, "argv", ["prog", "--type", summary_type]), \
             patch.object(summaries, "datetime", wraps=summaries.datetime) as mock_datetime, \
             patch.object(summaries, "get_last_post_date", return_value=None), \
             patch.object(summaries.requests, "get", side_effect=fake_get), \
             patch.object(summaries, "post_to_bluesky") as mock_post:
            mock_datetime.now.return_value = fake_now
            mock_datetime.strptime.side_effect = datetime.strptime
            summaries.main()
        return mock_post

    def test_skips_report_in_off_season(self):
        self.run_main("pitching", schedule("Oct 28"), date(2026, 11, 20)).assert_not_called()

    def test_skips_report_before_first_game(self):
        self.run_main("batting", schedule(upcoming=["Mar 26"]), date(2027, 3, 20)).assert_not_called()

    def test_posts_report_after_all_star_break(self):
        rows = schedule("Jul 12", upcoming=["Jul 17"])
        self.run_main("pitching", rows, date(2026, 7, 16)).assert_called_once()


if __name__ == "__main__":
    unittest.main()
