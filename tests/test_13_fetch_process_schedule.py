import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def load_schedule_module():
    with patch("boto3.Session") as mock_session:
        mock_session.return_value.resource.return_value = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "schedule_under_test",
            os.path.join(REPO_ROOT, "scripts", "13_fetch_process_schedule.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


schedule = load_schedule_module()
CT = ZoneInfo("America/Chicago")


def game(date, game_date, opp, home, state="Final", mil_score=None, opp_score=None,
         if_necessary="N", tbd=False, detailed=None):
    mil = {"team": {"id": 158, "name": "Milwaukee Brewers"}, "score": mil_score}
    other = {"team": {"id": 999, "name": opp}, "score": opp_score}
    return {
        "officialDate": date,
        "gameDate": game_date,
        "startTimeTBD": tbd,
        "ifNecessary": if_necessary,
        "status": {"abstractGameState": state, "detailedState": detailed or state},
        "teams": {"home": mil if home else other, "away": other if home else mil},
    }


class BuildScheduleTests(unittest.TestCase):
    def test_postseason_games_are_split_by_status(self):
        games = [
            game("2026-10-07", "2026-10-08T02:00:00Z", "San Diego Padres", home=False, mil_score=3, opp_score=1),
            game("2026-10-11", "2026-10-12T00:00:00Z", "Los Angeles Dodgers", home=True, state="Preview", detailed="Scheduled"),
        ]
        df = schedule.build_schedule(games, CT)
        last = df[df.placement == "last"].iloc[0]
        nxt = df[df.placement == "next"].iloc[0]
        self.assertEqual((last.date, last.opp_name, last.home_away, last.result, last.game_start),
                         ("Oct 7", "San Diego Padres", "away", "win", "3-1"))
        self.assertEqual((nxt.date, nxt.opp_name, nxt.home_away, nxt.result, nxt.game_start),
                         ("Oct 11", "Los Angeles Dodgers", "home", "--", "7:00 PM"))

    def test_loss_is_recorded(self):
        games = [game("2026-10-06", "2026-10-07T01:30:00Z", "San Diego Padres", home=False, mil_score=3, opp_score=4)]
        self.assertEqual(schedule.build_schedule(games, CT).iloc[0].result, "loss")

    def test_if_necessary_and_tbd_flags(self):
        games = [game("2026-10-16", "2026-10-17T01:00:00Z", "Los Angeles Dodgers", home=False,
                      state="Preview", detailed="Scheduled", if_necessary="Y", tbd=True)]
        row = schedule.build_schedule(games, CT).iloc[0]
        self.assertTrue(row.if_necessary)
        self.assertEqual(row.game_start, "TBD")

    def test_postponed_games_are_skipped(self):
        games = [game("2026-04-01", "2026-04-01T23:00:00Z", "Chicago Cubs", home=True,
                      state="Preview", detailed="Postponed")]
        self.assertTrue(schedule.build_schedule(games, CT).empty)

    def test_tables_hold_ten_games_each(self):
        past = [game(f"2026-09-{d:02d}", f"2026-09-{d:02d}T23:00:00Z", "St. Louis Cardinals", home=True,
                     mil_score=2, opp_score=1) for d in range(1, 16)]
        future = [game(f"2026-10-{d:02d}", f"2026-10-{d:02d}T23:00:00Z", "Los Angeles Dodgers", home=True,
                       state="Preview", detailed="Scheduled") for d in range(11, 26)]
        df = schedule.build_schedule(past + future, CT)
        self.assertEqual((df.placement == "last").sum(), 10)
        self.assertEqual((df.placement == "next").sum(), 10)
        self.assertEqual(df[df.placement == "last"].iloc[-1].date, "Sep 15")
        self.assertEqual(df[df.placement == "next"].iloc[0].date, "Oct 11")


if __name__ == "__main__":
    unittest.main()
