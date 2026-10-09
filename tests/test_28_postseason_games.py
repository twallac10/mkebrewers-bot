import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytz

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def load_postseason_module():
    with patch("boto3.Session") as mock_session:
        mock_session.return_value.resource.return_value = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "postseason_under_test",
            os.path.join(REPO_ROOT, "scripts", "28_fetch_postseason_stats.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


postseason = load_postseason_module()
CT = pytz.timezone("America/Chicago")


def game(game_type, number, game_date, opp, home, final=True, mil=None, other=None,
         decisions=None, probables=(None, None), if_necessary="N"):
    mil_side = {"team": {"id": 158, "name": "Milwaukee Brewers"}, "score": mil}
    opp_side = {"team": {"id": 999, "name": opp}, "score": other}
    if probables[0]:
        mil_side["probablePitcher"] = {"id": probables[0]}
    if probables[1]:
        opp_side["probablePitcher"] = {"id": probables[1]}
    return {
        "gamePk": number, "gameType": game_type, "seriesGameNumber": number, "gameDate": game_date,
        "ifNecessary": if_necessary, "venue": {"name": "Ballpark"},
        "status": {"abstractGameState": "Final" if final else "Preview", "detailedState": "Final" if final else "Scheduled"},
        "decisions": decisions or {},
        "teams": {"home": mil_side if home else opp_side, "away": opp_side if home else mil_side},
    }


class SummarizePostseasonGamesTests(unittest.TestCase):
    def test_log_and_next_game(self):
        games = [
            game("D", 1, "2026-10-04T00:30:00Z", "San Diego Padres", home=True, mil=3, other=2,
                 decisions={"winner": {"fullName": "DL Hall"}, "loser": {"fullName": "Adrian Morejon"},
                            "save": {"fullName": "Trevor Megill"}}),
            game("D", 2, "2026-10-07T01:30:00Z", "San Diego Padres", home=False, mil=3, other=4),
            game("L", 1, "2026-10-12T00:00:00Z", "Los Angeles Dodgers", home=True, final=False, probables=(11, 22)),
            game("L", 2, "2026-10-12T21:00:00Z", "Los Angeles Dodgers", home=True, final=False),
        ]
        log, nxt = postseason.summarize_postseason_games(games, CT)
        self.assertEqual([(r["round"], r["game_number"], r["result"], r["score"]) for r in log],
                         [("NLDS", 1, "win", "3-2"), ("NLDS", 2, "loss", "3-4")])
        self.assertEqual((log[0]["winning_pitcher"], log[0]["save_pitcher"]), ("DL Hall", "Trevor Megill"))
        self.assertEqual(log[1]["home_away"], "away")
        self.assertEqual((nxt["round"], nxt["game_number"], nxt["date"], nxt["day"], nxt["start_time"]),
                         ("NLCS", 1, "Oct 11", "Sunday", "7:00 PM"))
        self.assertEqual((nxt["brewers_probable"], nxt["opponent_probable"]), (11, 22))
        # No NLCS games played yet, so the series is 0-0
        self.assertEqual((nxt["series_wins"], nxt["series_losses"]), (0, 0))

    def test_series_score_counts_current_round_only(self):
        games = [
            game("D", 1, "2026-10-04T00:30:00Z", "San Diego Padres", home=True, mil=3, other=2),
            game("L", 1, "2026-10-12T00:00:00Z", "Los Angeles Dodgers", home=True, mil=1, other=5),
            game("L", 2, "2026-10-12T21:00:00Z", "Los Angeles Dodgers", home=True, final=False),
        ]
        _, nxt = postseason.summarize_postseason_games(games, CT)
        self.assertEqual((nxt["game_number"], nxt["series_wins"], nxt["series_losses"]), (2, 0, 1))

    def test_no_upcoming_game(self):
        games = [game("D", 1, "2026-10-04T00:30:00Z", "San Diego Padres", home=True, mil=3, other=2)]
        log, nxt = postseason.summarize_postseason_games(games, CT)
        self.assertEqual(len(log), 1)
        self.assertIsNone(nxt)


if __name__ == "__main__":
    unittest.main()
