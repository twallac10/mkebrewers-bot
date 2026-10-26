import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.championship import championship_sentence, find_championship


def journey(ws_status, ws_result):
    return [
        {"round": "Wild Card", "status": "bye", "opponent": "", "result": "Top-two seed"},
        {"round": "NLDS", "status": "completed", "opponent": "San Diego Padres", "result": "MIL wins 3-1"},
        {"round": "NLCS", "status": "completed", "opponent": "Los Angeles Dodgers", "result": "MIL wins 4-0"},
        {"round": "World Series", "status": ws_status, "opponent": "Tampa Bay Rays", "result": ws_result},
    ]


class FindChampionshipTest(unittest.TestCase):
    def test_won_world_series(self):
        ws = find_championship(journey("completed", "MIL wins 4-1"))
        self.assertEqual(ws["opponent"], "Tampa Bay Rays")

    def test_series_still_in_progress(self):
        self.assertIsNone(find_championship(journey("in_progress", "MIL leads 3-1")))

    def test_lost_world_series(self):
        self.assertIsNone(find_championship(journey("completed", "TB wins 4-3")))

    def test_no_data(self):
        self.assertIsNone(find_championship(None))
        self.assertIsNone(find_championship([]))


class ChampionshipSentenceTest(unittest.TestCase):
    def test_sentence(self):
        text = championship_sentence(journey("completed", "MIL wins 4-1")[3])
        self.assertEqual(
            text,
            "The Brewers are <span class='highlight'>World Series champions</span>, beating the "
            "<span class='highlight'>Tampa Bay Rays</span> <span class='highlight'>4-1</span> "
            "for the first title in franchise history.",
        )


if __name__ == "__main__":
    unittest.main()
