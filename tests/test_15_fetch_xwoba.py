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

    def test_skips_entry_with_person_none(self):
        roster_entries = [
            {"person": None, "position": {"abbreviation": "LF"}},
        ]
        result = xwoba.build_hitter_records(roster_entries, {})
        self.assertEqual(result, [])


class FetchHittingStatsTests(unittest.TestCase):
    def test_returns_pa_by_id_on_success(self):
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "people": [
                {"id": 661388, "stats": [{"splits": [{"stat": {"plateAppearances": "429"}}]}]},
                {"id": 694192, "stats": [{"splits": [{"stat": {"plateAppearances": "332"}}]}]},
            ]
        }
        with patch.object(xwoba.requests, "get", return_value=fake_response) as mock_get:
            result = xwoba.fetch_hitting_stats([661388, 694192])
        self.assertEqual(result, {"661388": 429, "694192": 332})
        mock_get.assert_called_once()

    def test_player_with_no_stats_yet_is_omitted(self):
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"people": [{"id": 668731, "stats": []}]}
        with patch.object(xwoba.requests, "get", return_value=fake_response):
            result = xwoba.fetch_hitting_stats([668731])
        self.assertEqual(result, {})

    def test_returns_none_on_failed_request(self):
        fake_response = MagicMock()
        fake_response.status_code = 500
        fake_response.text = "server error"
        with patch.object(xwoba.requests, "get", return_value=fake_response):
            result = xwoba.fetch_hitting_stats([661388])
        self.assertIsNone(result)

    def test_empty_id_list_returns_empty_dict_without_request(self):
        with patch.object(xwoba.requests, "get") as mock_get:
            result = xwoba.fetch_hitting_stats([])
        self.assertEqual(result, {})
        mock_get.assert_not_called()


class FetchPlayerIdsIntegrationTests(unittest.TestCase):
    def _roster_response(self):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {
            "roster": [
                {"person": {"id": 668930, "fullName": "Brice Turang"}, "position": {"abbreviation": "2B"}},
                {"person": {"id": 661388, "fullName": "William Contreras"}, "position": {"abbreviation": "C"}},
                {"person": {"id": 676879, "fullName": "Aaron Ashby"}, "position": {"abbreviation": "P"}},
            ]
        }
        return fake

    def _stats_response(self):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {
            "people": [
                {"id": 668930, "stats": [{"splits": [{"stat": {"plateAppearances": "458"}}]}]},
                {"id": 661388, "stats": [{"splits": [{"stat": {"plateAppearances": "429"}}]}]},
            ]
        }
        return fake

    def test_full_selection_excludes_pitcher_and_ranks_by_pa(self):
        with patch.object(xwoba, "PIN_BATTERS", []), patch.object(xwoba, "TOP_N", 2):
            with patch.object(
                xwoba.requests,
                "get",
                side_effect=[self._roster_response(), self._stats_response()],
            ):
                result = xwoba.fetch_player_ids()
        self.assertEqual(result, {"Brice Turang": "668930", "William Contreras": "661388"})

    def test_falls_back_to_pins_only_when_stats_fetch_fails(self):
        failed_stats = MagicMock()
        failed_stats.status_code = 500
        failed_stats.text = "server error"
        with patch.object(xwoba, "PIN_BATTERS", ["William Contreras"]):
            with patch.object(
                xwoba.requests, "get", side_effect=[self._roster_response(), failed_stats]
            ):
                result = xwoba.fetch_player_ids()
        self.assertEqual(result, {"William Contreras": "661388"})

    def test_returns_empty_dict_when_stats_fail_and_no_pins(self):
        failed_stats = MagicMock()
        failed_stats.status_code = 500
        failed_stats.text = "server error"
        with patch.object(xwoba, "PIN_BATTERS", []):
            with patch.object(
                xwoba.requests, "get", side_effect=[self._roster_response(), failed_stats]
            ):
                result = xwoba.fetch_player_ids()
        self.assertEqual(result, {})

    def test_returns_empty_dict_when_roster_fetch_fails(self):
        failed_roster = MagicMock()
        failed_roster.status_code = 500
        failed_roster.text = "server error"
        with patch.object(xwoba.requests, "get", return_value=failed_roster), patch.object(
            xwoba.time, "sleep"
        ):
            result = xwoba.fetch_player_ids()
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
