#!/usr/bin/env python3
"""Quickr – the minibar/dock window."""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

# Allow running directly or as part of the package
_SRC = Path(__file__).parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import config as cfg
import icons as ico

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

CSS = b"""
/* ---- Quickr Minibar ---- */
.quickr-bar {
    background-color: rgba(18, 18, 18, 0.96);
    border-top: 1px solid rgba(255,255,255,0.08);
}

.quickr-btn {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px;
    margin: 0 1px;
    min-width: 0;
    min-height: 0;
}

.quickr-btn:hover {
    background-color: rgba(255, 255, 255, 0.10);
}

.quickr-btn:active {
    background-color: rgba(255, 255, 255, 0.18);
}

tooltip {
    background-color: #1e1e1e;
    color: #dddddd;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
}
"""

ICON_SIZE   = 28   # px – icon inside the button
BUTTON_PAD  = 8    # px horizontal gap between buttons
BAR_HEIGHT  = 48   # px


# ---------------------------------------------------------------------------
# Open helpers
# ---------------------------------------------------------------------------

def _open_shortcut(shortcut: dict) -> None:
    stype = shortcut.get("type", "")
    path  = shortcut.get("path", "")

    if stype == "url":
        webbrowser.open(path)
    elif stype == "app":
        if path.endswith(".desktop"):
            subprocess.Popen(["gtk-launch", os.path.basename(path)[:-8]])
        else:
            subprocess.Popen([path], start_new_session=True)
    elif stype in ("file", "folder"):
        subprocess.Popen(["xdg-open", path], start_new_session=True)
    else:
        subprocess.Popen(["xdg-open", path], start_new_session=True)


# ---------------------------------------------------------------------------
# QuickrBar window
# ---------------------------------------------------------------------------

class QuickrBar(Gtk.Window):
    def __init__(self):
        super().__init__()
        self._apply_style()
        self._build_window()
        self._build_bar()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _apply_style(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_window(self):
        self.set_title("Quickr")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.stick()

        # Dock hint so window managers treat it like a panel
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)

        screen = Gdk.Screen.get_default()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)

        self.connect("destroy", Gtk.main_quit)
        self.connect("draw", self._on_draw)

    def _on_draw(self, _widget, cr):
        # Transparent background for compositing environments
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)  # CAIRO_OPERATOR_CLEAR
        cr.paint()
        cr.set_operator(2)  # CAIRO_OPERATOR_OVER
        return False

    def _build_bar(self):
        # Outer box carries the CSS class
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer.get_style_context().add_class("quickr-bar")
        outer.set_margin_top(0)
        outer.set_margin_bottom(0)

        # Inner scroll / button row
        self._btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=BUTTON_PAD,
        )
        self._btn_box.set_margin_start(12)
        self._btn_box.set_margin_end(12)
        self._btn_box.set_margin_top(4)
        self._btn_box.set_margin_bottom(4)

        outer.pack_start(self._btn_box, False, False, 0)
        self.add(outer)

        self._load_shortcuts()
        self._position()
        self.show_all()

    # ------------------------------------------------------------------
    # Shortcut buttons
    # ------------------------------------------------------------------

    def _load_shortcuts(self):
        # Remove old buttons
        for child in self._btn_box.get_children():
            self._btn_box.remove(child)

        shortcuts = cfg.get_shortcuts()
        if not shortcuts:
            lbl = Gtk.Label(label="No shortcuts – run: quickr editor")
            lbl.set_opacity(0.45)
            self._btn_box.pack_start(lbl, False, False, 0)
        else:
            for shortcut in shortcuts:
                btn = self._make_button(shortcut)
                self._btn_box.pack_start(btn, False, False, 0)

        self._btn_box.show_all()
        self._position()

    def _make_button(self, shortcut: dict) -> Gtk.Button:
        btn = Gtk.Button()
        btn.get_style_context().add_class("quickr-btn")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_focus_on_click(False)
        btn.set_tooltip_text(shortcut.get("name", shortcut.get("path", "")))

        pixbuf = ico.get_icon(shortcut, ICON_SIZE)
        if pixbuf is None:
            pixbuf = ico.get_placeholder_pixbuf(ICON_SIZE)

        img = Gtk.Image.new_from_pixbuf(pixbuf)
        btn.add(img)

        # For URLs, show a small label overlay below the icon
        if shortcut.get("type") == "url":
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            btn.remove(img)
            vbox.pack_start(img, False, False, 0)
            domain = _domain_label(shortcut.get("path", ""))
            if domain:
                lbl = Gtk.Label(label=domain)
                lbl.set_opacity(0.65)
                lbl.override_font(
                    _pango_desc("7")
                )
                vbox.pack_start(lbl, False, False, 0)
            btn.add(vbox)

        btn.connect("clicked", self._on_btn_clicked, shortcut)
        return btn

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_btn_clicked(self, _btn, shortcut):
        try:
            _open_shortcut(shortcut)
        except Exception as e:
            _show_error(self, str(e))

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _position(self):
        screen = Gdk.Screen.get_default()
        mon    = screen.get_primary_monitor()
        geom   = screen.get_monitor_geometry(mon)

        self._btn_box.show_all()
        # Force layout to get natural size
        self._btn_box.queue_resize()
        _w, _h = self.get_preferred_size()
        # Measure natural width
        nat_w = self._btn_box.get_preferred_width()[1]
        nat_w += 24  # margins

        bar_w = max(nat_w, 120)
        bar_x = geom.x + (geom.width - bar_w) // 2
        bar_y = geom.y + geom.height - BAR_HEIGHT

        self.set_default_size(bar_w, BAR_HEIGHT)
        self.resize(bar_w, BAR_HEIGHT)
        self.move(bar_x, bar_y)

    # ------------------------------------------------------------------
    # Public: reload
    # ------------------------------------------------------------------

    def reload(self):
        self._load_shortcuts()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _domain_label(url: str) -> str:
    """Return a short domain label for a URL."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        return host.replace("www.", "")[:12]
    except Exception:
        return ""


def _pango_desc(size: str):
    from gi.repository import Pango
    return Pango.font_description_from_string(f"Sans {size}")


def _show_error(parent, msg: str):
    dlg = Gtk.MessageDialog(
        transient_for=parent,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text="Quickr error",
    )
    dlg.format_secondary_text(msg)
    dlg.run()
    dlg.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    Gtk.main()


if __name__ == "__main__":
    bar = QuickrBar()
    main()
