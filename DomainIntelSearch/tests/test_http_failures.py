from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.crawlers import http_utils


class HttpFailureTests(unittest.TestCase):
    def setUp(self):
        http_utils.reset_feed_failures()

    @patch("src.crawlers.http_utils.requests.Session.get")
    def test_timeout_is_recorded_after_direct_and_proxy_attempts(self, get):
        get.side_effect = requests.Timeout("timed out")
        with self.assertRaises(requests.Timeout):
            http_utils.fetch_url("https://timeout.invalid/feed", name="Timeout feed")
        failures = http_utils.feed_failures()
        self.assertEqual(len(failures), 1)
        self.assertIn("Timeout", failures[0]["error"])

    @patch("src.crawlers.http_utils.requests.Session.get")
    def test_http_403_is_recorded_and_never_success(self, get):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        get.return_value = response
        with self.assertRaises(requests.HTTPError):
            http_utils.fetch_url("https://forbidden.invalid/feed", name="Forbidden feed")
        self.assertEqual(http_utils.feed_successes(), [])
        self.assertEqual(len(http_utils.feed_failures()), 1)

    @patch("src.crawlers.http_utils.feedparser.parse")
    @patch("src.crawlers.http_utils.fetch_url")
    def test_malformed_feed_is_failed_not_empty_success(self, fetch, parse):
        fetch.return_value = Mock(content=b"not xml")
        parse.return_value = Mock(bozo=True, entries=[], bozo_exception="bad xml")
        self.assertIsNone(http_utils.parse_feed(
            "https://malformed.invalid/feed", name="Malformed feed"))
        self.assertEqual(http_utils.feed_successes(), [])
        self.assertEqual(len(http_utils.feed_failures()), 1)


if __name__ == "__main__":
    unittest.main()
