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


if __name__ == "__main__":
    unittest.main()
