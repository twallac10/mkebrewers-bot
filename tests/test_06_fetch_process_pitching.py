import contextlib
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@contextlib.contextmanager
def _isolated_cwd():
    """Run in a throwaway temp directory so the script's local file writes
    (data/pitching/*.csv etc.) never touch the real repo tree."""
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        os.chdir(tmp_dir)
        # Mirrors the workflow's "Create necessary directories" step
        # (.github/workflows/fetch.yml), which the script relies on rather
        # than creating this directory itself.
        os.makedirs("data/pitching", exist_ok=True)
        try:
            yield tmp_dir
        finally:
            os.chdir(original_cwd)


def load_pitching_module(read_html_return, roster_response=None):
    """
    Import scripts/06_fetch_process_pitching.py and run its main() in
    isolation: no live Baseball-Reference fetch, no live MLB Stats API call,
    no real AWS calls, and any local file writes land in a temp directory.
    """
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

    if roster_response is None:
        roster_response = MagicMock()
        roster_response.status_code = 200
        roster_response.json.return_value = {"roster": []}

    with patch("boto3.Session") as mock_session, \
         patch("pandas.read_html", side_effect=lambda *a, **k: [df.copy() for df in read_html_return]), \
         patch("requests.get", return_value=roster_response):
        mock_session.return_value.resource.return_value = MagicMock()

        spec = importlib.util.spec_from_file_location(
            "fetch_pitching_under_test",
            os.path.join(REPO_ROOT, "scripts", "06_fetch_process_pitching.py"),
        )
        module = importlib.util.module_from_spec(spec)
        with _isolated_cwd():
            spec.loader.exec_module(module)
            module.main()
    return module


MINIMAL_BR_TABLE = pd.DataFrame({
    "Rk": ["1", "Rk", ""],
    "Player": ["Jacob Misiorowski", "Player", "Team Totals"],
    "Pos": ["SP", None, None],
    "IP": ["120.0", None, None],
    "ERA+": ["267", None, None],
    "FIP": ["2.04", None, None],
    "SO/BB": ["6.61", None, None],
})


class MainSmokeTest(unittest.TestCase):
    def test_main_runs_without_error(self):
        module = load_pitching_module(read_html_return=[MINIMAL_BR_TABLE])
        self.assertTrue(hasattr(module, "main"))


class CleanBrNameTests(unittest.TestCase):
    def test_strips_il_status_and_asterisk(self):
        module = load_pitching_module(read_html_return=[MINIMAL_BR_TABLE])
        self.assertEqual(
            module.clean_br_name("Kyle Harrison (15-day IL)*"), "kyle harrison"
        )

    def test_strips_forty_man_tag(self):
        module = load_pitching_module(read_html_return=[MINIMAL_BR_TABLE])
        self.assertEqual(
            module.clean_br_name("Coleman Crow (40-man)"), "coleman crow"
        )

    def test_plain_name_unchanged_besides_case(self):
        module = load_pitching_module(read_html_return=[MINIMAL_BR_TABLE])
        self.assertEqual(
            module.clean_br_name("Jacob Misiorowski"), "jacob misiorowski"
        )


class FetchCurrentRosterNamesTests(unittest.TestCase):
    def test_returns_normalized_names_on_success(self):
        roster_response = MagicMock()
        roster_response.status_code = 200
        roster_response.json.return_value = {
            "roster": [
                {"person": {"id": 694819, "fullName": "Jacob Misiorowski"}, "position": {"abbreviation": "P"}},
                {"person": {"id": 605540, "fullName": "Brandon Woodruff"}, "position": {"abbreviation": "P"}},
            ]
        }
        module = load_pitching_module(
            read_html_return=[MINIMAL_BR_TABLE], roster_response=roster_response
        )
        with patch("requests.get", return_value=roster_response):
            self.assertEqual(
                module.fetch_current_roster_names(),
                {"jacob misiorowski", "brandon woodruff"},
            )

    def test_returns_empty_set_on_failure(self):
        failed_response = MagicMock()
        failed_response.status_code = 500
        failed_response.text = "server error"
        module = load_pitching_module(
            read_html_return=[MINIMAL_BR_TABLE], roster_response=failed_response
        )
        with patch("requests.get", return_value=failed_response):
            self.assertEqual(module.fetch_current_roster_names(), set())


class RosterFilterIntegrationTests(unittest.TestCase):
    def test_drops_player_no_longer_on_roster(self):
        table = pd.DataFrame({
            "Rk": ["1", "2", "Rk", ""],
            "Player": ["Jacob Misiorowski", "Jake Woodford", "Player", "Team Totals"],
            "Pos": ["SP", None, None, None],
            "IP": ["120.0", "23.1", None, None],
            "ERA+": ["267", "61", None, None],
            "FIP": ["2.04", "6.94", None, None],
            "SO/BB": ["6.61", "2.86", None, None],
        })
        roster_response = MagicMock()
        roster_response.status_code = 200
        roster_response.json.return_value = {
            "roster": [
                {"person": {"id": 694819, "fullName": "Jacob Misiorowski"}, "position": {"abbreviation": "P"}},
            ]
        }
        module = load_pitching_module(
            read_html_return=[table], roster_response=roster_response
        )
        names = module.players["player"].tolist()
        self.assertIn("Jacob Misiorowski", names)
        self.assertNotIn("Jake Woodford", names)

    def test_keeps_annotated_name_of_rostered_il_player(self):
        table = pd.DataFrame({
            "Rk": ["1", "2", "Rk", ""],
            "Player": ["Jacob Misiorowski", "Brandon Woodruff (60-day IL)", "Player", "Team Totals"],
            "Pos": ["SP", "SP", None, None],
            "IP": ["120.0", "45.1", None, None],
            "ERA+": ["267", "142", None, None],
            "FIP": ["2.04", "2.98", None, None],
            "SO/BB": ["6.61", "4.70", None, None],
        })
        roster_response = MagicMock()
        roster_response.status_code = 200
        roster_response.json.return_value = {
            "roster": [
                {"person": {"id": 694819, "fullName": "Jacob Misiorowski"}, "position": {"abbreviation": "P"}},
                {"person": {"id": 605540, "fullName": "Brandon Woodruff"}, "position": {"abbreviation": "P"}},
            ]
        }
        module = load_pitching_module(
            read_html_return=[table], roster_response=roster_response
        )
        names = module.players["player"].tolist()
        self.assertIn("Brandon Woodruff (60-day IL)", names)

    def test_falls_back_to_unfiltered_when_roster_fetch_fails(self):
        table = pd.DataFrame({
            "Rk": ["1", "2", "Rk", ""],
            "Player": ["Jacob Misiorowski", "Jake Woodford", "Player", "Team Totals"],
            "Pos": ["SP", None, None, None],
            "IP": ["120.0", "23.1", None, None],
            "ERA+": ["267", "61", None, None],
            "FIP": ["2.04", "6.94", None, None],
            "SO/BB": ["6.61", "2.86", None, None],
        })
        failed_response = MagicMock()
        failed_response.status_code = 500
        failed_response.text = "server error"
        module = load_pitching_module(
            read_html_return=[table], roster_response=failed_response
        )
        names = module.players["player"].tolist()
        self.assertIn("Jacob Misiorowski", names)
        self.assertIn("Jake Woodford", names)


if __name__ == "__main__":
    unittest.main()
