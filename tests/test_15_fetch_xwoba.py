import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def load_xwoba_module():
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    with patch("boto3.Session") as mock_session:
        mock_session.return_value.resource.return_value = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "fetch_xwoba_under_test",
            os.path.join(REPO_ROOT, "scripts", "15_fetch_xwoba.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


xwoba = load_xwoba_module()


class MatchPinsTests(unittest.TestCase):
    def setUp(self):
        self.hitters = [
            {"name": "William Contreras", "id": "661388", "pa": 429},
            {"name": "Jackson Chourio", "id": "694192", "pa": 332},
            {"name": "Sal Frelick", "id": "686217", "pa": 313},
        ]

    def test_exact_match_is_pinned(self):
        result = xwoba.match_pins(self.hitters, ["Sal Frelick"])
        self.assertEqual(result, {"Sal Frelick": "686217"})

    def test_fuzzy_first_name_prefix_match(self):
        result = xwoba.match_pins(self.hitters, ["Will Contreras"])
        self.assertEqual(result, {"William Contreras": "661388"})

    def test_unmatched_pin_is_skipped(self):
        result = xwoba.match_pins(self.hitters, ["Willy Adames"])
        self.assertEqual(result, {})

    def test_multiple_pins(self):
        result = xwoba.match_pins(self.hitters, ["Sal Frelick", "Jackson Chourio"])
        self.assertEqual(
            result, {"Sal Frelick": "686217", "Jackson Chourio": "694192"}
        )


class SelectTopBattersTests(unittest.TestCase):
    def setUp(self):
        self.hitters = [
            {"name": "Brice Turang", "id": "668930", "pa": 458},
            {"name": "William Contreras", "id": "661388", "pa": 429},
            {"name": "Jake Bauers", "id": "641343", "pa": 381},
            {"name": "Garrett Mitchell", "id": "669003", "pa": 350},
            {"name": "Jackson Chourio", "id": "694192", "pa": 332},
            {"name": "Blake Perkins", "id": "663368", "pa": 101},
        ]

    def test_selects_top_n_by_plate_appearances(self):
        result = xwoba.select_top_batters(self.hitters, pin_names=[], top_n=3)
        self.assertEqual(
            result,
            {
                "Brice Turang": "668930",
                "William Contreras": "661388",
                "Jake Bauers": "641343",
            },
        )

    def test_pinned_player_included_even_with_low_pa(self):
        result = xwoba.select_top_batters(
            self.hitters, pin_names=["Blake Perkins"], top_n=3
        )
        self.assertEqual(len(result), 3)
        self.assertIn("Blake Perkins", result)
        self.assertIn("Brice Turang", result)
        self.assertIn("William Contreras", result)

    def test_top_n_larger_than_roster_returns_everyone(self):
        result = xwoba.select_top_batters(self.hitters, pin_names=[], top_n=50)
        self.assertEqual(len(result), len(self.hitters))


class BuildHitterRecordsTests(unittest.TestCase):
    def test_excludes_pitchers(self):
        roster_entries = [
            {"person": {"id": 1, "fullName": "Some Pitcher"}, "position": {"abbreviation": "P"}},
            {"person": {"id": 2, "fullName": "Some Hitter"}, "position": {"abbreviation": "LF"}},
        ]
        result = xwoba.build_hitter_records(roster_entries, {"2": 100})
        self.assertEqual(result, [{"name": "Some Hitter", "id": "2", "pa": 100}])

    def test_missing_stats_default_to_zero(self):
        roster_entries = [
            {"person": {"id": 3, "fullName": "New Callup"}, "position": {"abbreviation": "CF"}},
        ]
        result = xwoba.build_hitter_records(roster_entries, {})
        self.assertEqual(result, [{"name": "New Callup", "id": "3", "pa": 0}])

    def test_skips_malformed_entry(self):
        roster_entries = [
            {"person": {"id": 4}, "position": {"abbreviation": "1B"}},  # missing fullName
        ]
        result = xwoba.build_hitter_records(roster_entries, {})
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
