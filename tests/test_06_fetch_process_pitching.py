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
         patch("pandas.read_html", return_value=read_html_return), \
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


if __name__ == "__main__":
    unittest.main()
