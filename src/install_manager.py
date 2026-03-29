#!/usr/bin/env python3
"""Quickr – Install Manager dialog.

Fetches all GitHub releases, shows each version with a status badge
(CURRENT / NEWER / OLDER) and lets the user upgrade or downgrade.
"""

import sys
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

_SRC = Path(__file__).parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import updater as upd

# ---------------------------------------------------------------------------
# CSS for the Install Manager
# ---------------------------------------------------------------------------

_CSS = b"""
.im-header {
    font-size: 15px;
    font-weight: bold;
    color: #e0e0e0;
}
.im-subheader {
    font-size: 11px;
    color: #888888;
}
.im-version-row {
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
    padding: 6px 10px;
    margin: 2px 0;
}
.im-badge-current {
    background: rgba(100,220,100,0.18);
    color: #80e880;
    border-radius: 4px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: bold;
}
.im-badge-newer {
    background: rgba(255,200,50,0.18);
    color: #ffc832;
    border-radius: 4px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: bold;
}
.im-badge-older {
    background: rgba(160,160,160,0.14);
    color: #aaaaaa;
    border-radius: 4px;
    padding: 1px 7px;
    font-size: 10px;
}
.im-action-btn {
    background: rgba(100,180,255,0.15);
    border: 1px solid rgba(100,180,255,0.35);
    border-radius: 6px;
    color: #90c8ff;
    padding: 3px 12px;
    font-size: 11px;
    min-width: 80px;
}
.im-action-btn:hover {
    background: rgba(100,180,255,0.28);
}
.im-action-btn:disabled {
    opacity: 0.4;
}
.im-progress-bar {
    min-height: 6px;
    border-radius: 3px;
}
"""


class InstallManagerDialog(Gtk.Dialog):
    """GTK dialog that lists all GitHub releases and supports install/downgrade."""

    def __init__(self, parent=None):
        super().__init__(title="Quickr – Install Manager", transient_for=parent, flags=0)
        self.set_modal(True)
        self.set_default_size(500, 400)
        self.set_resizable(True)

        # Apply CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._row_widgets: list = []   # list of (release_dict, action_btn)

        self._build_ui()
        self._start_fetch()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        content = self.get_content_area()
        content.set_spacing(0)

        # ── Header bar ────────────────────────────────────────────────
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_box.set_margin_top(16)
        header_box.set_margin_bottom(10)
        header_box.set_margin_start(20)
        header_box.set_margin_end(20)

        title_lbl = Gtk.Label(label="Install Manager")
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.get_style_context().add_class("im-header")
        header_box.pack_start(title_lbl, False, False, 0)

        self._sub_lbl = Gtk.Label(label=f"Current version: v{upd.VERSION}  •  Fetching releases…")
        self._sub_lbl.set_halign(Gtk.Align.START)
        self._sub_lbl.get_style_context().add_class("im-subheader")
        header_box.pack_start(self._sub_lbl, False, False, 0)

        content.pack_start(header_box, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_bottom(6)
        content.pack_start(sep, False, False, 0)

        # ── Spinner (shown while loading) ─────────────────────────────
        self._spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._spinner_box.set_margin_top(30)
        self._spinner_box.set_margin_bottom(30)

        spinner = Gtk.Spinner()
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.start()
        self._spinner_box.pack_start(spinner, False, False, 0)

        loading_lbl = Gtk.Label(label="Fetching releases from GitHub…")
        loading_lbl.set_halign(Gtk.Align.CENTER)
        loading_lbl.get_style_context().add_class("im-subheader")
        self._spinner_box.pack_start(loading_lbl, False, False, 0)

        content.pack_start(self._spinner_box, True, True, 0)

        # ── Scrollable release list (hidden until loaded) ─────────────
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_margin_start(12)
        self._scroll.set_margin_end(12)
        self._scroll.set_no_show_all(True)

        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._list_box.set_margin_top(4)
        self._list_box.set_margin_bottom(4)
        self._scroll.add(self._list_box)

        content.pack_start(self._scroll, True, True, 0)

        # ── Error label (hidden until needed) ─────────────────────────
        self._error_lbl = Gtk.Label()
        self._error_lbl.set_halign(Gtk.Align.CENTER)
        self._error_lbl.set_margin_top(20)
        self._error_lbl.set_no_show_all(True)
        self._error_lbl.get_style_context().add_class("im-subheader")
        content.pack_start(self._error_lbl, False, False, 0)

        # ── Progress bar (hidden during normal browsing) ───────────────
        self._prog_bar = Gtk.ProgressBar()
        self._prog_bar.get_style_context().add_class("im-progress-bar")
        self._prog_bar.set_margin_start(20)
        self._prog_bar.set_margin_end(20)
        self._prog_bar.set_margin_bottom(8)
        self._prog_bar.set_no_show_all(True)
        content.pack_start(self._prog_bar, False, False, 0)

        # ── Close button ──────────────────────────────────────────────
        self.add_button("Close", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda _d, _r: self.destroy())

        self.show_all()

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _start_fetch(self):
        """Start a background thread to fetch all releases."""
        def _worker():
            releases = upd.get_all_releases()
            GLib.idle_add(self._on_fetch_done, releases)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_fetch_done(self, releases) -> bool:
        """Called on GTK thread once releases have been fetched."""
        self._spinner_box.hide()

        if releases is None:
            self._error_lbl.set_text(
                "Could not reach the GitHub API.\n"
                "Check your internet connection and try again."
            )
            self._error_lbl.show()
            self._sub_lbl.set_text(f"Current version: v{upd.VERSION}  •  Network error")
            return False

        if not releases:
            self._error_lbl.set_text(
                "No releases found on GitHub."
            )
            self._error_lbl.show()
            self._sub_lbl.set_text(f"Current version: v{upd.VERSION}  •  No releases found")
            return False

        newer_count = sum(1 for r in releases if r["status"] == "newer")
        if newer_count:
            self._sub_lbl.set_text(
                f"Current version: v{upd.VERSION}  •  {newer_count} newer version(s) available"
            )
        else:
            self._sub_lbl.set_text(
                f"Current version: v{upd.VERSION}  •  You are up to date"
            )

        for release in releases:
            row = self._build_release_row(release)
            self._list_box.pack_start(row, False, True, 0)

        self._list_box.show_all()
        self._scroll.show()
        return False

    # ------------------------------------------------------------------
    # Release row
    # ------------------------------------------------------------------

    def _build_release_row(self, release: dict) -> Gtk.Box:
        """Build a single horizontal row for a release entry."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.get_style_context().add_class("im-version-row")
        row.set_margin_start(4)
        row.set_margin_end(4)

        # Version label
        ver_lbl = Gtk.Label(label=f"v{release['version']}")
        ver_lbl.set_halign(Gtk.Align.START)
        ver_lbl.set_width_chars(10)
        ver_lbl.set_xalign(0.0)
        attr = Pango.AttrList()
        attr.insert(Pango.attr_weight_new(Pango.Weight.SEMIBOLD))
        ver_lbl.set_attributes(attr)
        row.pack_start(ver_lbl, False, False, 0)

        # Status badge
        status = release["status"]
        badge_lbl = Gtk.Label()
        if status == "current":
            badge_lbl.set_text("● CURRENT")
            badge_lbl.get_style_context().add_class("im-badge-current")
        elif status == "newer":
            badge_lbl.set_text("▲ NEWER")
            badge_lbl.get_style_context().add_class("im-badge-newer")
        else:
            badge_lbl.set_text("▼ OLDER")
            badge_lbl.get_style_context().add_class("im-badge-older")
        badge_lbl.set_halign(Gtk.Align.START)
        row.pack_start(badge_lbl, False, False, 4)

        # Spacer
        spacer = Gtk.Box()
        row.pack_start(spacer, True, True, 0)

        # Action button
        btn = Gtk.Button()
        btn.get_style_context().add_class("im-action-btn")
        btn.set_relief(Gtk.ReliefStyle.NONE)

        if status == "current":
            btn.set_label("Installed")
            btn.set_sensitive(False)
        elif status == "newer":
            btn.set_label("Upgrade")
        else:
            btn.set_label("Downgrade")

        btn.connect("clicked", self._on_action_clicked, release, btn)
        row.pack_start(btn, False, False, 0)

        self._row_widgets.append((release, btn))
        return row

    # ------------------------------------------------------------------
    # Install / downgrade action
    # ------------------------------------------------------------------

    def _on_action_clicked(self, _btn, release: dict, btn: Gtk.Button) -> None:
        """Handle Upgrade / Downgrade button click."""
        if not upd.is_appimage():
            self._show_non_appimage_instructions(release)
            return

        if not release.get("download_url"):
            self._show_no_asset_dialog(release)
            return

        action = "upgrade" if release["status"] == "newer" else "downgrade"
        confirm = self._confirm_dialog(
            f"{'Upgrade' if action == 'upgrade' else 'Downgrade'} to v{release['version']}?",
            f"This will {'upgrade' if action == 'upgrade' else 'downgrade'} Quickr "
            f"from v{upd.VERSION} to v{release['version']}.\n"
            "Quickr will need to be restarted afterwards.",
        )
        if not confirm:
            return

        self._lock_all_buttons()
        btn.set_label("Installing…")
        self._run_install(release, btn)

    def _run_install(self, release: dict, btn: Gtk.Button) -> None:
        """Download the selected release AppImage in a background thread."""
        self._prog_bar.set_fraction(0.0)
        self._prog_bar.show()

        install_ok: bool = False
        pulse_source_id: list[int | None] = [None]

        def _pulse() -> bool:
            self._prog_bar.pulse()
            return True

        # Start pulsing until we get size info
        pulse_source_id[0] = GLib.timeout_add(80, _pulse)

        def _progress_cb(done: int, total: int) -> None:
            if total > 0:
                GLib.idle_add(self._prog_bar.set_fraction, done / total)

        def _worker() -> None:
            nonlocal install_ok
            install_ok = upd.do_appimage_update(release["download_url"], _progress_cb)
            GLib.idle_add(_finish)

        def _finish() -> None:
            if pulse_source_id[0] is not None:
                GLib.source_remove(pulse_source_id[0])
                pulse_source_id[0] = None
            self._prog_bar.hide()
            self._unlock_all_buttons()

            if install_ok:
                self._show_success(release["version"])
            else:
                btn.set_label("Upgrade" if release["status"] == "newer" else "Downgrade")
                self._show_error_dialog(
                    f"Download failed.\nVisit: {upd.RELEASES_PAGE}"
                )

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Button locking helpers
    # ------------------------------------------------------------------

    def _lock_all_buttons(self) -> None:
        for _r, b in self._row_widgets:
            b.set_sensitive(False)

    def _unlock_all_buttons(self) -> None:
        for r, b in self._row_widgets:
            if r["status"] != "current":
                b.set_sensitive(True)

    # ------------------------------------------------------------------
    # Dialog helpers
    # ------------------------------------------------------------------

    def _confirm_dialog(self, title: str, msg: str) -> bool:
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=title,
        )
        dlg.format_secondary_text(msg)
        response = dlg.run()
        dlg.destroy()
        return response == Gtk.ResponseType.OK

    def _show_success(self, version: str) -> None:
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=f"Quickr v{version} installed",
        )
        dlg.format_secondary_text(
            "The new version has been installed.\n"
            "Please restart Quickr to apply the update."
        )
        dlg.run()
        dlg.destroy()
        self.destroy()

    def _show_error_dialog(self, msg: str) -> None:
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Installation failed",
        )
        dlg.format_secondary_text(msg)
        dlg.run()
        dlg.destroy()

    def _show_no_asset_dialog(self, release: dict) -> None:
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=f"No AppImage for v{release['version']}",
        )
        dlg.format_secondary_text(
            f"The release v{release['version']} does not include an AppImage asset.\n"
            f"Visit the releases page to download it manually:\n{upd.RELEASES_PAGE}"
        )
        dlg.run()
        dlg.destroy()

    def _show_non_appimage_instructions(self, release: dict) -> None:
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=f"Switch to v{release['version']}",
        )
        dlg.format_secondary_text(
            "Automatic installation is only supported for AppImage builds.\n\n"
            "To switch version manually:\n"
            "  cd <quickr-directory>\n"
            f"  git checkout v{release['version']}\n"
            "  bash install.sh\n\n"
            f"Or download the AppImage from:\n{upd.RELEASES_PAGE}"
        )
        dlg.run()
        dlg.destroy()


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def open_install_manager(parent=None) -> None:
    """Create and show the Install Manager dialog (non-blocking)."""
    dlg = InstallManagerDialog(parent=parent)
    dlg.run()
