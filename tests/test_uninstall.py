#!/usr/bin/env python3
"""Tests for Quickr – quickr uninstall command."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure the repo root is on the path so we can import quickr.py directly
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import quickr as qr


class TestCmdUninstall(unittest.TestCase):
    """Tests for _cmd_uninstall() in quickr.py."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._home = Path(self._tmpdir.name)

        # Paths that install.sh would have created
        self._bin       = self._home / ".local" / "bin"
        self._autostart = self._home / ".config" / "autostart"
        self._apps      = self._home / ".local" / "share" / "applications"
        self._config    = self._home / ".config" / "quickr"

        for d in (self._bin, self._autostart, self._apps, self._config):
            d.mkdir(parents=True, exist_ok=True)

        (self._bin / "quickr").write_text(
            "#!/usr/bin/env bash\nexec python3 /home/user/Quickr/quickr.py \"$@\"\n"
        )
        (self._autostart / "quickr.desktop").write_text("[Desktop Entry]\n")
        (self._apps / "quickr.desktop").write_text("[Desktop Entry]\n")
        (self._config / "shortcuts.json").write_text("{}")

    def tearDown(self):
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _run_uninstall(self, confirm_config="n"):
        """Run _cmd_uninstall(), redirecting home and answering prompts."""
        with patch.object(Path, "home", return_value=self._home):
            with patch("builtins.input", return_value=confirm_config):
                with patch("subprocess.run"):  # suppress update-desktop-database
                    qr._cmd_uninstall()

    # ------------------------------------------------------------------
    # installed files are removed
    # ------------------------------------------------------------------

    def test_removes_bin_wrapper(self):
        self._run_uninstall()
        self.assertFalse((self._bin / "quickr").exists())

    def test_removes_autostart_entry(self):
        self._run_uninstall()
        self.assertFalse((self._autostart / "quickr.desktop").exists())

    def test_removes_applications_entry(self):
        self._run_uninstall()
        self.assertFalse((self._apps / "quickr.desktop").exists())

    # ------------------------------------------------------------------
    # config directory: kept when user declines, removed when confirmed
    # ------------------------------------------------------------------

    def test_keeps_config_when_declined(self):
        self._run_uninstall(confirm_config="n")
        self.assertTrue(self._config.is_dir())

    def test_removes_config_when_confirmed(self):
        self._run_uninstall(confirm_config="y")
        self.assertFalse(self._config.exists())

    # ------------------------------------------------------------------
    # no installed files: should not raise
    # ------------------------------------------------------------------

    def test_nothing_to_remove_does_not_raise(self):
        # Remove the installed files first so there is nothing to uninstall
        (self._bin / "quickr").unlink()
        (self._autostart / "quickr.desktop").unlink()
        (self._apps / "quickr.desktop").unlink()
        shutil.rmtree(self._config)

        try:
            with patch.object(Path, "home", return_value=self._home):
                with patch("builtins.input", side_effect=EOFError):
                    with patch("subprocess.run"):
                        qr._cmd_uninstall()
        except SystemExit:
            self.fail("_cmd_uninstall raised SystemExit unexpectedly")

    # ------------------------------------------------------------------
    # source directory is never touched
    # ------------------------------------------------------------------

    def test_source_directory_not_removed(self):
        """The repo directory (parent of quickr.py) must not be deleted."""
        source_dir = Path(__file__).parent.parent
        self._run_uninstall()
        self.assertTrue(source_dir.is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
