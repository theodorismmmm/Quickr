#!/usr/bin/env python3
"""Tests for Quickr – config module."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import config as cfg


class TestConfig(unittest.TestCase):
    def setUp(self):
        """Point config at a temporary directory so tests are isolated."""
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self._orig_cfg_dir   = cfg.CONFIG_DIR
        self._orig_cfg_file  = cfg.CONFIG_FILE
        self._orig_set_file  = cfg.SETTINGS_FILE
        cfg.CONFIG_DIR    = tmp_path
        cfg.CONFIG_FILE   = tmp_path / "shortcuts.json"
        cfg.SETTINGS_FILE = tmp_path / "settings.json"

    def tearDown(self):
        cfg.CONFIG_DIR    = self._orig_cfg_dir
        cfg.CONFIG_FILE   = self._orig_cfg_file
        cfg.SETTINGS_FILE = self._orig_set_file
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # load / save
    # ------------------------------------------------------------------

    def test_load_creates_empty_config(self):
        data = cfg.load()
        self.assertEqual(data, {"shortcuts": []})
        self.assertTrue(cfg.CONFIG_FILE.exists())

    def test_load_returns_existing_config(self):
        cfg.CONFIG_FILE.write_text(
            json.dumps({"shortcuts": [{"id": "x", "type": "app", "name": "A", "path": "/a"}]})
        )
        data = cfg.load()
        self.assertEqual(len(data["shortcuts"]), 1)

    def test_load_recovers_from_corrupt_json(self):
        cfg.CONFIG_FILE.write_text("INVALID JSON{{{{")
        data = cfg.load()
        self.assertEqual(data, {"shortcuts": []})

    # ------------------------------------------------------------------
    # add_shortcut
    # ------------------------------------------------------------------

    def test_add_shortcut_all_types(self):
        for t in cfg.SHORTCUT_TYPES:
            entry = cfg.add_shortcut(f"Name {t}", t, f"/path/{t}")
            self.assertEqual(entry["type"], t)
            self.assertEqual(entry["name"], f"Name {t}")
            self.assertIn("id", entry)

    def test_add_shortcut_invalid_type(self):
        with self.assertRaises(ValueError):
            cfg.add_shortcut("Bad", "invalid_type", "/tmp")

    def test_add_shortcut_strips_whitespace(self):
        entry = cfg.add_shortcut("  Padded  ", "app", "  /bin/app  ")
        self.assertEqual(entry["name"], "Padded")
        self.assertEqual(entry["path"], "/bin/app")

    def test_add_shortcut_persists(self):
        cfg.add_shortcut("Persist", "file", "/tmp/f")
        # Re-load from disk
        data = json.loads(cfg.CONFIG_FILE.read_text())
        names = [s["name"] for s in data["shortcuts"]]
        self.assertIn("Persist", names)

    # ------------------------------------------------------------------
    # get_shortcuts
    # ------------------------------------------------------------------

    def test_get_shortcuts_empty(self):
        self.assertEqual(cfg.get_shortcuts(), [])

    def test_get_shortcuts_returns_list(self):
        cfg.add_shortcut("A", "app", "/a")
        cfg.add_shortcut("B", "url", "https://b.com")
        shortcuts = cfg.get_shortcuts()
        self.assertEqual(len(shortcuts), 2)

    # ------------------------------------------------------------------
    # update_shortcut
    # ------------------------------------------------------------------

    def test_update_shortcut(self):
        entry = cfg.add_shortcut("Old Name", "app", "/old")
        ok = cfg.update_shortcut(entry["id"], "New Name", "url", "https://new.com")
        self.assertTrue(ok)
        updated = next(s for s in cfg.get_shortcuts() if s["id"] == entry["id"])
        self.assertEqual(updated["name"], "New Name")
        self.assertEqual(updated["type"], "url")
        self.assertEqual(updated["path"], "https://new.com")

    def test_update_shortcut_nonexistent(self):
        ok = cfg.update_shortcut("nonexistent-id", "X", "app", "/x")
        self.assertFalse(ok)

    def test_update_shortcut_invalid_type(self):
        entry = cfg.add_shortcut("A", "app", "/a")
        with self.assertRaises(ValueError):
            cfg.update_shortcut(entry["id"], "A", "bad_type", "/a")

    # ------------------------------------------------------------------
    # remove_shortcut
    # ------------------------------------------------------------------

    def test_remove_shortcut(self):
        e1 = cfg.add_shortcut("Keep", "app", "/keep")
        e2 = cfg.add_shortcut("Remove", "app", "/remove")
        ok = cfg.remove_shortcut(e2["id"])
        self.assertTrue(ok)
        ids = [s["id"] for s in cfg.get_shortcuts()]
        self.assertIn(e1["id"], ids)
        self.assertNotIn(e2["id"], ids)

    def test_remove_shortcut_nonexistent(self):
        ok = cfg.remove_shortcut("does-not-exist")
        self.assertFalse(ok)


class TestSettings(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self._orig_cfg_dir   = cfg.CONFIG_DIR
        self._orig_cfg_file  = cfg.CONFIG_FILE
        self._orig_set_file  = cfg.SETTINGS_FILE
        cfg.CONFIG_DIR    = tmp_path
        cfg.CONFIG_FILE   = tmp_path / "shortcuts.json"
        cfg.SETTINGS_FILE = tmp_path / "settings.json"

    def tearDown(self):
        cfg.CONFIG_DIR    = self._orig_cfg_dir
        cfg.CONFIG_FILE   = self._orig_cfg_file
        cfg.SETTINGS_FILE = self._orig_set_file
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # get_settings
    # ------------------------------------------------------------------

    def test_get_settings_returns_defaults_when_missing(self):
        s = cfg.get_settings()
        self.assertAlmostEqual(s["transparency"], cfg.DEFAULT_SETTINGS["transparency"])
        self.assertEqual(s["icon_size"], cfg.DEFAULT_SETTINGS["icon_size"])
        self.assertEqual(s["bar_height"], cfg.DEFAULT_SETTINGS["bar_height"])
        self.assertEqual(s["builtin_widgets"], [])

    def test_get_settings_merges_with_defaults(self):
        # Write a partial settings file
        cfg.SETTINGS_FILE.write_text(json.dumps({"transparency": 0.5}))
        s = cfg.get_settings()
        self.assertAlmostEqual(s["transparency"], 0.5)
        # Defaults for unspecified keys are preserved
        self.assertEqual(s["icon_size"], cfg.DEFAULT_SETTINGS["icon_size"])

    def test_get_settings_recovers_from_corrupt_json(self):
        cfg.SETTINGS_FILE.write_text("NOT JSON{{")
        s = cfg.get_settings()
        self.assertEqual(s, cfg.DEFAULT_SETTINGS)

    # ------------------------------------------------------------------
    # save_settings
    # ------------------------------------------------------------------

    def test_save_and_reload_settings(self):
        data = dict(cfg.DEFAULT_SETTINGS)
        data["transparency"] = 0.42
        data["icon_size"] = 32
        data["builtin_widgets"] = ["clock", "date"]
        cfg.save_settings(data)

        loaded = cfg.get_settings()
        self.assertAlmostEqual(loaded["transparency"], 0.42)
        self.assertEqual(loaded["icon_size"], 32)
        self.assertEqual(loaded["builtin_widgets"], ["clock", "date"])

    def test_save_settings_persists_to_disk(self):
        cfg.save_settings({"transparency": 0.7})
        raw = json.loads(cfg.SETTINGS_FILE.read_text())
        self.assertAlmostEqual(raw["transparency"], 0.7)

    def test_browser_default_in_defaults(self):
        s = cfg.get_settings()
        self.assertIn("browser", s)
        self.assertEqual(s["browser"], "default")

    def test_browser_saved_and_loaded(self):
        settings = cfg.get_settings()
        settings["browser"] = "chrome"
        cfg.save_settings(settings)
        loaded = cfg.get_settings()
        self.assertEqual(loaded["browser"], "chrome")

    def test_browser_options_contains_expected_values(self):
        for opt in ("default", "chrome", "chromium", "firefox"):
            self.assertIn(opt, cfg.BROWSER_OPTIONS)


class TestSudoFlag(unittest.TestCase):
    """Tests for the per-shortcut sudo flag."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self._orig_cfg_dir   = cfg.CONFIG_DIR
        self._orig_cfg_file  = cfg.CONFIG_FILE
        self._orig_set_file  = cfg.SETTINGS_FILE
        cfg.CONFIG_DIR    = tmp_path
        cfg.CONFIG_FILE   = tmp_path / "shortcuts.json"
        cfg.SETTINGS_FILE = tmp_path / "settings.json"

    def tearDown(self):
        cfg.CONFIG_DIR    = self._orig_cfg_dir
        cfg.CONFIG_FILE   = self._orig_cfg_file
        cfg.SETTINGS_FILE = self._orig_set_file
        self._tmpdir.cleanup()

    def test_add_shortcut_sudo_false_by_default(self):
        entry = cfg.add_shortcut("App", "app", "/usr/bin/app")
        self.assertFalse(entry.get("sudo", False))

    def test_add_shortcut_sudo_true(self):
        entry = cfg.add_shortcut("App", "app", "/usr/bin/app", sudo=True)
        self.assertTrue(entry["sudo"])

    def test_sudo_flag_persisted(self):
        entry = cfg.add_shortcut("Sudo App", "app", "/usr/bin/app", sudo=True)
        loaded = next(s for s in cfg.get_shortcuts() if s["id"] == entry["id"])
        self.assertTrue(loaded["sudo"])

    def test_update_shortcut_sets_sudo(self):
        entry = cfg.add_shortcut("App", "app", "/usr/bin/app", sudo=False)
        cfg.update_shortcut(entry["id"], "App", "app", "/usr/bin/app", sudo=True)
        updated = next(s for s in cfg.get_shortcuts() if s["id"] == entry["id"])
        self.assertTrue(updated["sudo"])

    def test_update_shortcut_clears_sudo(self):
        entry = cfg.add_shortcut("App", "app", "/usr/bin/app", sudo=True)
        cfg.update_shortcut(entry["id"], "App", "app", "/usr/bin/app", sudo=False)
        updated = next(s for s in cfg.get_shortcuts() if s["id"] == entry["id"])
        self.assertFalse(updated["sudo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
