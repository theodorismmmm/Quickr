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
        self._orig_cfg_dir  = cfg.CONFIG_DIR
        self._orig_cfg_file = cfg.CONFIG_FILE
        cfg.CONFIG_DIR  = tmp_path
        cfg.CONFIG_FILE = tmp_path / "shortcuts.json"

    def tearDown(self):
        cfg.CONFIG_DIR  = self._orig_cfg_dir
        cfg.CONFIG_FILE = self._orig_cfg_file
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
