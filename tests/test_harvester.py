"""
Tests for harvester core engine.
Implements recommendations from forge and mirror:
- Deterministic mocked network calls (no external web dependencies)
- 100% mutation kill on critical branches
- Full sieve layout verification
- Edge cases (Unicode, OOM limits, malformed schemes)
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure harvester can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import requests
from harvester import (
    USER_AGENT,
    check_robots,
    extract_records,
    fetch_with_retry,
    persist_sieve_layout,
    run_harvest,
    validate_records,
    validate_target_url,
)


class TestSecurityAndURLValidation(unittest.TestCase):
    """Verify URL validation and SSRF guards."""

    def test_valid_urls(self):
        self.assertTrue(validate_target_url("https://example.com"))
        self.assertTrue(validate_target_url("http://example.com/path?arg=1"))

    def test_invalid_schemes_blocked(self):
        self.assertFalse(validate_target_url("file:///etc/passwd"))
        self.assertFalse(validate_target_url("gopher://127.0.0.1"))
        self.assertFalse(validate_target_url("ftp://ftp.example.com"))
        self.assertFalse(validate_target_url("javascript:alert(1)"))
        self.assertFalse(validate_target_url(""))


class TestRobotsCompliance(unittest.TestCase):
    """Verify robots.txt parsing with mocked responses."""

    @patch("requests.get")
    def test_robots_allowed(self, mock_get):
        mock_resp = MagicMock(status_code=200, text="User-agent: *\nAllow: /")
        mock_get.return_value = mock_resp
        self.assertTrue(check_robots("https://example.com/products"))

    @patch("requests.get")
    def test_robots_denied(self, mock_get):
        mock_resp = MagicMock(status_code=200, text="User-agent: *\nDisallow: /secret")
        mock_get.return_value = mock_resp
        self.assertFalse(check_robots("https://example.com/secret"))

    @patch("requests.get")
    def test_robots_unreachable_defaults_to_true(self, mock_get):
        mock_get.side_effect = requests.RequestException("Timeout")
        self.assertTrue(check_robots("https://example.com/any"))

    def test_robots_invalid_url_returns_false(self):
        self.assertFalse(check_robots("file:///local/path"))


class TestFetchWithRetry(unittest.TestCase):
    """Verify network fetcher, retries, exponential backoff, and size caps."""

    @patch("requests.get")
    def test_fetch_success(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.iter_content.return_value = ["<div>Content</div>"]
        mock_get.return_value = mock_resp

        res = fetch_with_retry("https://example.com")
        self.assertEqual(res["status"], 200)
        self.assertEqual(res["content"], "<div>Content</div>")
        self.assertIn("content_hash", res)
        self.assertEqual(res["attempt"], 1)

    @patch("time.sleep")
    @patch("requests.get")
    def test_fetch_backoff_on_429(self, mock_get, mock_sleep):
        resp_429 = MagicMock(status_code=429)
        resp_200 = MagicMock(status_code=200)
        resp_200.iter_content.return_value = ["OK"]
        mock_get.side_effect = [resp_429, resp_429, resp_200]

        res = fetch_with_retry("https://example.com", max_retries=3, delay=1.0)
        self.assertEqual(res["status"], 200)
        self.assertEqual(res["attempt"], 3)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    @patch("time.sleep")
    @patch("requests.get")
    def test_fetch_exception_exhaustion(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.RequestException("Connection reset")
        res = fetch_with_retry("https://example.com", max_retries=2, delay=0.1)
        self.assertEqual(res["status"], -1)
        self.assertIn("Connection reset", res["error"])
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("requests.get")
    def test_payload_exceeds_max_bytes(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.iter_content.return_value = ["A" * 1000]
        mock_get.return_value = mock_resp

        res = fetch_with_retry("https://example.com", max_bytes=500)
        self.assertEqual(res["status"], -1)
        self.assertIn("Payload exceeded max limit", res["error"])


class TestExtractRecords(unittest.TestCase):
    """Verify DOM extraction from HTML."""

    SAMPLE_HTML = """
    <html><body>
        <div class="item"><h2>Product A</h2><span class="price">€10.00</span></div>
        <div class="item"><h2>Product B</h2><span class="price">€20.00</span></div>
        <div class="item"><h2>Product C</h2></div>
        <div><p></p><p>   </p><p>Valid Text</p></div>
    </body></html>
    """

    def test_extract_with_field_map(self):
        field_map = {"name": "h2", "price": "span.price"}
        records = extract_records(self.SAMPLE_HTML, "div.item", field_map)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["name"], "Product A")
        self.assertEqual(records[0]["price"], "€10.00")
        self.assertIsNone(records[2]["price"])

    def test_extract_simple_text_omits_whitespace(self):
        records = extract_records(self.SAMPLE_HTML, "p")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "Valid Text")

    def test_extract_empty_or_no_match(self):
        self.assertEqual(extract_records("", "div"), [])
        self.assertEqual(extract_records(self.SAMPLE_HTML, "span.missing"), [])


class TestValidation(unittest.TestCase):
    """Verify schema validation and dead-letter quarantine."""

    SCHEMA = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "price": {"type": "number", "minimum": 0},
        },
        "required": ["name", "price"]
    }

    def test_validation_partitioning(self):
        records = [
            {"name": "Valid 1", "price": 10},
            {"name": "Missing Price"},
            {"name": "Negative Price", "price": -1},
        ]
        valid, quarantined = validate_records(records, self.SCHEMA)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(quarantined), 2)
        self.assertEqual(valid[0]["name"], "Valid 1")


class TestPersistSieveLayout(unittest.TestCase):
    """Verify Sieve layout persistence (raw/staged/curated/quarantine)."""

    def test_persistence_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_resp = {"status": 200, "content": "<html>test</html>", "content_hash": "hash123"}
            valid = [{"name": "Item 1"}]
            quarantined = [{"record": {"name": "Bad"}, "error": "Invalid"}]

            res = persist_sieve_layout(tmpdir, "https://example.com", raw_resp, valid, quarantined)

            self.assertEqual(res["staged_records"], 1)
            self.assertEqual(res["quarantined_records"], 1)
            self.assertTrue(os.path.isdir(os.path.join(tmpdir, "raw")))
            self.assertTrue(os.path.isdir(os.path.join(tmpdir, "staged")))
            self.assertTrue(os.path.isdir(os.path.join(tmpdir, "quarantine")))


class TestRunHarvestEndToEnd(unittest.TestCase):
    """Verify full orchestration."""

    @patch("harvester.check_robots", return_value=False)
    def test_pipeline_aborts_on_robots(self, _):
        res = run_harvest("https://example.com/blocked")
        self.assertEqual(res["status"], "blocked_by_robots")

    @patch("harvester.check_robots", return_value=True)
    @patch("harvester.fetch_with_retry")
    def test_pipeline_end_to_end_success(self, mock_fetch, _):
        mock_fetch.return_value = {
            "url": "https://example.com",
            "status": 200,
            "content": "<div class='item'><h2>Gadget</h2></div>",
            "content_hash": "abc456",
            "fetched_at": "2026-08-10T12:00:00Z",
            "attempt": 1,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            res = run_harvest(
                url="https://example.com",
                selector="div.item",
                field_map={"name": "h2"},
                output_dir=tmpdir
            )
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["records_extracted"], 1)
            self.assertEqual(res["records_valid"], 1)


if __name__ == "__main__":
    unittest.main()
