#!/usr/bin/env python3
"""Tests for Quickr – updater module."""

import json
import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path so we can import updater
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import updater as upd


class TestVersionParsing(unittest.TestCase):
    """Tests for the internal version comparison helper."""

    def test_parse_simple(self):
        self.assertEqual(upd._parse_version("1.2.3"), (1, 2, 3))

    def test_parse_with_leading_v(self):
        self.assertEqual(upd._parse_version("v2.0.0"), (2, 0, 0))

    def test_parse_single_component(self):
        self.assertEqual(upd._parse_version("5"), (5,))

    def test_parse_invalid_returns_zero(self):
        self.assertEqual(upd._parse_version("not-a-version"), (0,))

    def test_comparison_newer(self):
        self.assertGreater(upd._parse_version("1.1.0"), upd._parse_version("1.0.0"))

    def test_comparison_same(self):
        self.assertEqual(upd._parse_version("1.0.0"), upd._parse_version("1.0.0"))

    def test_comparison_older(self):
        self.assertLess(upd._parse_version("0.9.9"), upd._parse_version("1.0.0"))


class TestVersionConstant(unittest.TestCase):
    """VERSION should be a non-empty string that parses to a valid tuple."""

    def test_version_is_string(self):
        self.assertIsInstance(upd.VERSION, str)

    def test_version_not_empty(self):
        self.assertTrue(upd.VERSION.strip())

    def test_version_parses(self):
        parsed = upd._parse_version(upd.VERSION)
        self.assertIsInstance(parsed, tuple)
        self.assertGreater(len(parsed), 0)


class TestIsAppImage(unittest.TestCase):
    """is_appimage() should reflect the APPIMAGE environment variable."""

    def test_not_appimage_when_env_absent(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPIMAGE", None)
            self.assertFalse(upd.is_appimage())

    def test_is_appimage_when_env_set(self):
        with patch.dict(os.environ, {"APPIMAGE": "/path/to/Quickr.AppImage"}):
            self.assertTrue(upd.is_appimage())


class TestGetLatestRelease(unittest.TestCase):
    """get_latest_release() should parse GitHub API responses correctly."""

    def _fake_response(self, tag: str, assets: list) -> MagicMock:
        payload = json.dumps({"tag_name": tag, "assets": assets}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_tag_and_appimage_url(self):
        assets = [
            {"name": "Quickr.AppImage", "browser_download_url": "https://example.com/Quickr.AppImage"},
        ]
        mock_resp = self._fake_response("v1.2.3", assets)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = upd.get_latest_release()
        self.assertIsNotNone(result)
        tag, url = result
        self.assertEqual(tag, "1.2.3")
        self.assertEqual(url, "https://example.com/Quickr.AppImage")

    def test_returns_none_for_appimage_url_when_no_asset(self):
        mock_resp = self._fake_response("v2.0.0", [])
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = upd.get_latest_release()
        self.assertIsNotNone(result)
        tag, url = result
        self.assertEqual(tag, "2.0.0")
        self.assertIsNone(url)

    def test_returns_none_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("no network")):
            result = upd.get_latest_release()
        self.assertIsNone(result)


class TestCheckForUpdates(unittest.TestCase):
    """check_for_updates() should return update info only when a newer
    version is available."""

    def _mock_release(self, tag: str, url=None):
        return patch.object(upd, "get_latest_release", return_value=(tag, url))

    def test_returns_none_when_up_to_date(self):
        with self._mock_release(upd.VERSION):
            result = upd.check_for_updates()
        self.assertIsNone(result)

    def test_returns_none_when_network_fails(self):
        with patch.object(upd, "get_latest_release", return_value=None):
            result = upd.check_for_updates()
        self.assertIsNone(result)

    def test_returns_info_when_newer_version(self):
        # Construct a version string that is definitely newer
        major = upd._parse_version(upd.VERSION)[0] + 1
        newer = f"{major}.0.0"
        dl_url = "https://example.com/Quickr.AppImage"
        with self._mock_release(newer, dl_url):
            result = upd.check_for_updates()
        self.assertIsNotNone(result)
        self.assertEqual(result["current"], upd.VERSION)
        self.assertEqual(result["latest"], newer)
        self.assertEqual(result["download_url"], dl_url)

    def test_returns_none_when_older_version_on_server(self):
        with self._mock_release("0.0.1"):
            result = upd.check_for_updates()
        self.assertIsNone(result)


class TestDoAppImageUpdate(unittest.TestCase):
    """do_appimage_update() should download and replace the AppImage binary."""

    def test_returns_false_when_not_appimage(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPIMAGE", None)
            result = upd.do_appimage_update("https://example.com/Quickr.AppImage")
        self.assertFalse(result)

    def test_successful_download_replaces_file(self):
        fake_content = b"fake appimage binary data"

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_appimage = os.path.join(tmpdir, "Quickr.AppImage")
            # Create a placeholder "current" AppImage
            with open(fake_appimage, "wb") as f:
                f.write(b"old content")

            mock_resp = MagicMock()
            mock_resp.read.side_effect = [fake_content, b""]
            mock_resp.headers = {"Content-Length": str(len(fake_content))}
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)

            with patch.dict(os.environ, {"APPIMAGE": fake_appimage}):
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    result = upd.do_appimage_update(
                        "https://example.com/Quickr.AppImage"
                    )

            self.assertTrue(result)
            with open(fake_appimage, "rb") as f:
                content = f.read()
            self.assertEqual(content, fake_content)

    def test_returns_false_on_download_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_appimage = os.path.join(tmpdir, "Quickr.AppImage")
            with open(fake_appimage, "wb") as f:
                f.write(b"original")

            with patch.dict(os.environ, {"APPIMAGE": fake_appimage}):
                with patch("urllib.request.urlopen", side_effect=OSError("fail")):
                    result = upd.do_appimage_update(
                        "https://example.com/Quickr.AppImage"
                    )

            self.assertFalse(result)
            # Original file should be untouched
            with open(fake_appimage, "rb") as f:
                self.assertEqual(f.read(), b"original")


if __name__ == "__main__":
    unittest.main()
