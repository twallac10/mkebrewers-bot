import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def load_abs_module():
    with patch("boto3.Session") as mock_session:
        mock_session.return_value.resource.return_value = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "fetch_abs_under_test",
            os.path.join(REPO_ROOT, "scripts", "30_fetch_abs_challenges.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


abs_mod = load_abs_module()

GAME = {"game_pk": 1, "game_date": "2026-10-04", "game_type": "D"}


def pitch(call, is_strike, balls, strikes, review=None):
    event = {
        "isPitch": True,
        "details": {"call": {"description": call}, "isStrike": is_strike, "type": {"description": "Sinker"}},
        "count": {"balls": balls, "strikes": strikes, "outs": 0},
        "pitchData": {"coordinates": {"pX": 0.1, "pZ": 2.5}},
    }
    if review:
        event["reviewDetails"] = review
    return event


def review(team_id, player_id, overturned):
    return {"isOverturned": overturned, "inProgress": False, "reviewType": "MJ",
            "challengeTeamId": team_id, "player": {"id": player_id, "fullName": f"Player {player_id}"}}


def feed(plays):
    return {
        "gameData": {"teams": {"home": {"id": 158, "abbreviation": "MIL"},
                               "away": {"id": 135, "abbreviation": "SD"}}},
        "liveData": {"plays": {"allPlays": plays}},
    }


def play(events, play_review=None, batter=10, pitcher=20):
    p = {"about": {"inning": 3, "halfInning": "top"},
         "matchup": {"batter": {"id": batter, "fullName": "Batter"}, "pitcher": {"id": pitcher, "fullName": "Pitcher"}},
         "playEvents": events}
    if play_review:
        p["reviewDetails"] = play_review
    return p


class ExtractChallengesTests(unittest.TestCase):
    def test_pitch_level_challenge_by_catcher(self):
        rows = abs_mod.extract_challenges(
            feed([play([pitch("Ball", False, 1, 0, review(158, 99, False))])]), GAME)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["challenging_team"], "brewers")
        self.assertEqual(row["challenger_role"], "Catcher")
        self.assertEqual(row["season_type"], "postseason")
        self.assertEqual(row["opponent"], "SD")
        self.assertEqual((row["balls"], row["strikes"]), (0, 0))
        self.assertEqual(row["original_call"], "Ball")

    def test_play_level_challenge_applies_to_final_pitch(self):
        # An overturned strike three: the feed shows the final call and the review on the play
        events = [pitch("Foul", True, 0, 1), pitch("Called Strike", True, 0, 3)]
        rows = abs_mod.extract_challenges(feed([play(events, review(135, 10, True))]), GAME)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["challenging_team"], "opponent")
        self.assertEqual(row["challenger_role"], "Batter")
        self.assertEqual(row["original_call"], "Ball")
        self.assertEqual(row["final_call"], "Called Strike")
        self.assertEqual((row["balls"], row["strikes"]), (0, 2))

    def test_non_abs_review_is_ignored(self):
        manager_review = dict(review(158, 99, True), reviewType="A")
        rows = abs_mod.extract_challenges(feed([play([pitch("Ball", False, 1, 0)], manager_review)]), GAME)
        self.assertEqual(rows, [])


class SummaryTests(unittest.TestCase):
    def test_splits_regular_and_postseason(self):
        regular = dict(GAME, game_pk=2, game_type="R")
        rows = (abs_mod.extract_challenges(feed([play([pitch("Ball", False, 1, 0, review(158, 99, True))])]), regular)
                + abs_mod.extract_challenges(feed([play([pitch("Ball", False, 1, 0, review(158, 99, False))])]), GAME))
        summary = abs_mod.build_summary(rows, [regular, GAME])
        self.assertEqual(summary["regular"]["brewers"]["overturned"], 1)
        self.assertEqual(summary["postseason"]["brewers"]["upheld"], 1)
        self.assertEqual(summary["postseason"]["games"], 1)
        innings = {i["inning"]: i for i in summary["regular"]["brewers_by_inning"]}
        self.assertEqual(innings["3"]["overturned"], 1)
        self.assertEqual(len(innings), 10)

    def test_player_split_into_offense_and_defense(self):
        # Player 99 challenges once while catching and once while batting
        plays = [play([pitch("Ball", False, 1, 0, review(158, 99, True))]),
                 play([pitch("Called Strike", True, 0, 1, review(158, 99, False))], batter=99)]
        rows = abs_mod.extract_challenges(feed(plays), GAME)
        player = abs_mod.build_summary(rows, [GAME])["postseason"]["brewers_by_player"][0]
        self.assertEqual(player["challenges"], 2)
        self.assertEqual((player["offense"]["challenges"], player["offense"]["overturned"]), (1, 0))
        self.assertEqual((player["defense"]["challenges"], player["defense"]["overturned"]), (1, 1))

    def test_extra_innings_are_grouped(self):
        self.assertEqual(abs_mod.inning_label(9), "9")
        self.assertEqual(abs_mod.inning_label(12), "10+")


if __name__ == "__main__":
    unittest.main()
