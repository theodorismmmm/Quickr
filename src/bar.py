#!/usr/bin/env python3
"""Quickr – the minibar/dock window."""

import datetime
import os
import subprocess
import sys
import time
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
import updater as upd

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def _make_css(transparency: float, notch_style: str = "standard") -> bytes:
    """Generate bar CSS with configurable background transparency and notch style."""
    alpha = max(0.0, min(1.0, transparency))
    if notch_style == "dynamic_island":
        bar_radius = "20px"
        bar_border = "none"
    else:
        bar_radius = "0 0 20px 20px"
        bar_border = "1px solid rgba(255,255,255,0.08)"
    return f"""
/* ---- Quickr Minibar ---- */
.quickr-bar {{
    background-color: rgba(12, 12, 12, {alpha:.2f});
    border-bottom: {bar_border};
    border-radius: {bar_radius};
}}

.quickr-btn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px;
    margin: 0 1px;
    min-width: 0;
    min-height: 0;
}}

.quickr-btn:hover {{
    background-color: rgba(255, 255, 255, 0.10);
}}

.quickr-btn:active {{
    background-color: rgba(255, 255, 255, 0.18);
}}

.quickr-builtin {{
    background: rgba(255,255,255,0.05);
    border-radius: 6px;
    padding: 2px 8px;
    margin: 0 2px;
    color: #e0e0e0;
}}

.quickr-update-btn {{
    background: rgba(255,255,255,0.06);
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
    margin: 0 2px;
    min-width: 0;
    min-height: 0;
    color: #aaaaaa;
    font-size: 11px;
}}

.quickr-update-btn:hover {{
    background-color: rgba(100,180,255,0.15);
    color: #e0e0e0;
}}

.quickr-update-btn:active {{
    background-color: rgba(100,180,255,0.25);
}}

.quickr-update-btn.has-update {{
    background: rgba(255,200,50,0.15);
    color: #ffc832;
}}

.quickr-update-btn.has-update:hover {{
    background: rgba(255,200,50,0.25);
}}

tooltip {{
    background-color: #1e1e1e;
    color: #dddddd;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
}}

.quickr-console-output {{
    background-color: rgba(8, 8, 8, 0.97);
    color: #00e676;
    border-radius: 4px;
    padding: 4px 6px;
    font-family: monospace;
    font-size: 10px;
}}

.quickr-console-btn {{
    background: rgba(255,255,255,0.06);
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
    margin: 0 2px;
    min-width: 0;
    min-height: 0;
    color: #aaaaaa;
    font-size: 11px;
    font-family: monospace;
}}

.quickr-console-btn:hover {{
    background-color: rgba(0,230,118,0.15);
    color: #00e676;
}}

.quickr-console-btn.active {{
    background-color: rgba(0,230,118,0.18);
    color: #00e676;
}}
""".encode()

BUTTON_PAD = 8   # px horizontal gap between buttons


# ---------------------------------------------------------------------------
# Built-in widget helpers
# ---------------------------------------------------------------------------

BUILTIN_LABELS = {
    "clock":     "Clock",
    "date":      "Date",
    "stopwatch": "Elapsed",
}

CONSOLE_EXTRA_HEIGHT = 120   # extra px added to bar height when console is visible


def _builtin_text(widget_id: str, start_time: float) -> str:
    now = datetime.datetime.now()
    if widget_id == "clock":
        return now.strftime("%H:%M:%S")
    elif widget_id == "date":
        return now.strftime("%d %b %Y")
    elif widget_id == "stopwatch":
        elapsed = int(time.monotonic() - start_time)
        h, rem = divmod(elapsed, 3600)
        m, s   = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    return ""


# ---------------------------------------------------------------------------
# Open helpers
# ---------------------------------------------------------------------------

def _open_shortcut(shortcut: dict) -> None:
    stype = shortcut.get("type", "")
    path  = shortcut.get("path", "")
    use_sudo = shortcut.get("sudo", False)

    if stype == "url":
        _open_url(path)
    elif stype == "app":
        if path.endswith(".desktop"):
            cmd = ["gtk-launch", os.path.basename(path)[:-8]]
            if use_sudo:
                cmd = ["pkexec"] + cmd
            subprocess.Popen(cmd)
        else:
            cmd = [path]
            if use_sudo:
                cmd = ["pkexec"] + cmd
            subprocess.Popen(cmd, start_new_session=True)
    elif stype in ("file", "folder"):
        subprocess.Popen(["xdg-open", path], start_new_session=True)
    else:
        subprocess.Popen(["xdg-open", path], start_new_session=True)


def _open_url(url: str) -> None:
    """Open a URL using the browser configured in settings."""
    settings = cfg.get_settings()
    chrome_only = settings.get("chrome_only", False)
    browser = "chrome" if chrome_only else settings.get("browser", "default")

    # Multiple candidate binary names per browser, tried in order.
    _BROWSER_CANDIDATES = {
        "chrome":   ["google-chrome-stable", "google-chrome", "chrome"],
        "chromium": ["chromium-browser", "chromium"],
        "firefox":  ["firefox"],
    }

    if browser in _BROWSER_CANDIDATES:
        for binary in _BROWSER_CANDIDATES[browser]:
            try:
                subprocess.Popen([binary, "--new-tab", url], start_new_session=True)
                return
            except FileNotFoundError:
                continue
        # None of the configured browser's binaries were found.
        if chrome_only:
            # No fallback allowed – surface a clear error to the user.
            raise RuntimeError(
                "Chrome not found. Install Google Chrome or disable Chrome-only mode in Settings."
            )
        # For other browsers, fall through to the system default.

    webbrowser.open(url)


# ---------------------------------------------------------------------------
# QuickrBar window
# ---------------------------------------------------------------------------

class QuickrBar(Gtk.Window):
    def __init__(self):
        super().__init__()
        self._settings     = cfg.get_settings()
        self._start_time   = time.monotonic()
        self._anim_opacity = 1.0
        self._builtin_labels: dict = {}   # widget_id -> Gtk.Label
        self._timer_id = None
        self._css_provider = Gtk.CssProvider()
        self._console_visible = False
        # Update state (AppImage only)
        self._update_info = None   # pending update metadata
        self._update_btn  = None
        self._apply_style()
        self._build_window()
        self._build_bar()
        self._setup_tray()
        # Show bar on startup (animated)
        if self._settings.get("show_on_startup", True):
            self._animate_show()
        # Schedule a background update check for AppImage users
        if upd.is_appimage():
            GLib.timeout_add_seconds(3, self._bg_check_for_updates)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _apply_style(self):
        transparency = self._settings.get("transparency", 0.96)
        notch_style  = self._settings.get("notch_style", "standard")
        self._css_provider.load_from_data(_make_css(transparency, notch_style))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def reload_style(self):
        """Re-apply CSS after a settings change."""
        self._settings = cfg.get_settings()
        transparency = self._settings.get("transparency", 0.96)
        notch_style  = self._settings.get("notch_style", "standard")
        self._css_provider.load_from_data(_make_css(transparency, notch_style))

    def _build_window(self):
        self.set_title("Quickr")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.stick()

        # POPUP_MENU hint: renders as a floating popup above other windows.
        # The original DOCK hint is kept optional here; POPUP_MENU suits the
        # show/hide tray-icon-driven workflow better.
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)

        screen = Gdk.Screen.get_default()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)

        self.connect("destroy", self._on_destroy)
        self.connect("draw", self._on_draw)
        self.connect("key-press-event", self._on_key_press)

    def _on_destroy(self, _w):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
        Gtk.main_quit()

    def _on_draw(self, _widget, cr):
        # Transparent background for compositing environments
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)  # CAIRO_OPERATOR_CLEAR
        cr.paint()
        cr.set_operator(2)  # CAIRO_OPERATOR_OVER
        return False

    def _build_bar(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.get_style_context().add_class("quickr-bar")

        # ── Button row ──────────────────────────────────────────────────
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer.set_margin_top(0)
        outer.set_margin_bottom(0)

        self._btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=BUTTON_PAD,
        )
        self._btn_box.set_margin_start(12)
        self._btn_box.set_margin_end(12)
        self._btn_box.set_margin_top(4)
        self._btn_box.set_margin_bottom(4)

        outer.pack_start(self._btn_box, False, False, 0)

        # Console toggle button (>_)
        self._console_btn = Gtk.Button(label=">_")
        self._console_btn.get_style_context().add_class("quickr-console-btn")
        self._console_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._console_btn.set_focus_on_click(False)
        self._console_btn.set_tooltip_text("Toggle mini console (Ctrl+`)")
        self._console_btn.connect("clicked", lambda _b: self._toggle_console())
        outer.pack_end(self._console_btn, False, False, 4)

        root.pack_start(outer, False, False, 0)

        # ── Console panel (hidden by default) ────────────────────────────
        self._console_panel = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4
        )
        self._console_panel.set_margin_start(10)
        self._console_panel.set_margin_end(10)
        self._console_panel.set_margin_top(2)
        self._console_panel.set_margin_bottom(6)
        self._console_panel.set_no_show_all(True)

        # Output text view
        self._console_buf = Gtk.TextBuffer()
        self._console_buf.set_text("Quickr mini-console (Ctrl+` to toggle)\n")
        console_view = Gtk.TextView(buffer=self._console_buf)
        console_view.set_editable(False)
        console_view.set_cursor_visible(False)
        console_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        console_view.get_style_context().add_class("quickr-console-output")

        scroll_out = Gtk.ScrolledWindow()
        scroll_out.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll_out.set_size_request(-1, 80)
        scroll_out.add(console_view)
        self._console_panel.pack_start(scroll_out, True, True, 0)
        self._console_view = console_view

        # Input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        prompt = Gtk.Label(label="$")
        prompt.set_opacity(0.6)
        input_row.pack_start(prompt, False, False, 2)

        self._console_entry = Gtk.Entry()
        self._console_entry.set_placeholder_text("enter command…")
        self._console_entry.set_hexpand(True)
        self._console_entry.connect("activate", self._on_console_cmd)
        input_row.pack_start(self._console_entry, True, True, 0)

        run_btn = Gtk.Button(label="Run")
        run_btn.get_style_context().add_class("quickr-console-btn")
        run_btn.connect("clicked", self._on_console_cmd)
        input_row.pack_start(run_btn, False, False, 0)

        self._console_panel.pack_start(input_row, False, False, 0)
        root.pack_start(self._console_panel, False, False, 0)

        self.add(root)
        self._load_shortcuts()

    # ------------------------------------------------------------------
    # System tray icon
    # ------------------------------------------------------------------

    def _setup_tray(self):
        """Create a StatusIcon in the system notification area."""
        self._tray = Gtk.StatusIcon()
        icon_path = Path(__file__).parent.parent / "AppDir" / "quickr.png"
        if icon_path.exists():
            self._tray.set_from_file(str(icon_path))
        else:
            # Fall back to a generic icon from the theme
            for name in ("view-app-grid-symbolic", "applications-other", "emblem-default"):
                try:
                    self._tray.set_from_icon_name(name)
                    break
                except GLib.Error:
                    pass
        self._tray.set_tooltip_text("Quickr – click to toggle")
        self._tray.set_visible(True)
        self._tray.connect("activate",   self._on_tray_activate)
        self._tray.connect("popup-menu", self._on_tray_menu)

    def _on_tray_activate(self, _tray):
        if self.get_visible():
            self._animate_hide()
        else:
            self._settings = cfg.get_settings()
            self.reload_style()
            self._load_shortcuts()
            self._animate_show()

    def _on_tray_menu(self, _tray, button, activate_time):
        menu = Gtk.Menu()

        item_editor = Gtk.MenuItem(label="Open Editor")
        item_editor.connect("activate", self._launch_editor)
        menu.append(item_editor)

        menu.append(Gtk.SeparatorMenuItem())

        item_update = Gtk.MenuItem(label="Check for Updates")
        item_update.connect("activate", lambda _: self._on_check_updates_clicked(None))
        menu.append(item_update)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit Quickr")
        item_quit.connect("activate", lambda _: Gtk.main_quit())
        menu.append(item_quit)

        menu.show_all()
        menu.popup(None, None, None, self._tray, button, activate_time)

    def _launch_editor(self, _item):
        script = Path(__file__).parent.parent / "quickr.py"
        subprocess.Popen(
            ["python3", str(script), "editor"],
            start_new_session=True,
        )

    # ------------------------------------------------------------------
    # Popup animation
    # ------------------------------------------------------------------

    def _animate_show(self):
        """Fade the bar in from transparent."""
        self._anim_opacity = 0.0
        self.set_opacity(0.0)
        self._position()
        self.show_all()
        GLib.timeout_add(16, self._tick_fade_in)

    def _tick_fade_in(self) -> bool:
        self._anim_opacity = min(1.0, self._anim_opacity + 0.08)
        self.set_opacity(self._anim_opacity)
        return self._anim_opacity < 1.0   # True → continue ticking

    def _animate_hide(self):
        """Fade the bar out to transparent then hide."""
        self._anim_opacity = self.get_opacity()
        GLib.timeout_add(16, self._tick_fade_out)

    def _tick_fade_out(self) -> bool:
        self._anim_opacity = max(0.0, self._anim_opacity - 0.08)
        self.set_opacity(self._anim_opacity)
        if self._anim_opacity <= 0.0:
            self.hide()
            return False
        return True

    # ------------------------------------------------------------------
    # Shortcut + built-in widget loading
    # ------------------------------------------------------------------

    def _load_shortcuts(self):
        for child in self._btn_box.get_children():
            self._btn_box.remove(child)
        self._builtin_labels.clear()
        self._update_btn = None

        # Cancel existing per-second timer
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        self._settings = cfg.get_settings()
        icon_size       = self._settings.get("icon_size", 28)
        bar_height      = self._settings.get("bar_height", 48)
        shortcuts       = cfg.get_shortcuts()
        enabled_builtins = self._settings.get("builtin_widgets", [])

        if not shortcuts and not enabled_builtins:
            lbl = Gtk.Label(label="No shortcuts – run: quickr editor")
            lbl.set_opacity(0.45)
            self._btn_box.pack_start(lbl, False, False, 0)
        else:
            for shortcut in shortcuts:
                btn = self._make_button(shortcut, icon_size)
                self._btn_box.pack_start(btn, False, False, 0)

            for widget_id in enabled_builtins:
                w = self._make_builtin_widget(widget_id)
                self._btn_box.pack_start(w, False, False, 0)

        # AppImage users get a persistent "Check for Updates" button
        if upd.is_appimage():
            self._update_btn = self._make_update_button()
            self._btn_box.pack_end(self._update_btn, False, False, 0)
            # Restore highlighted state if an update was already detected
            if self._update_info is not None:
                self._mark_update_available(self._update_info["latest"])

        self._btn_box.show_all()
        self._position(bar_height)

        if enabled_builtins:
            self._timer_id = GLib.timeout_add(1000, self._update_builtins)

    def _make_button(self, shortcut: dict, icon_size: int) -> Gtk.Button:
        btn = Gtk.Button()
        btn.get_style_context().add_class("quickr-btn")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_focus_on_click(False)
        btn.set_tooltip_text(shortcut.get("name", shortcut.get("path", "")))

        pixbuf = ico.get_icon(shortcut, icon_size)
        if pixbuf is None:
            pixbuf = ico.get_placeholder_pixbuf(icon_size)

        img = Gtk.Image.new_from_pixbuf(pixbuf)
        btn.add(img)

        if shortcut.get("type") == "url":
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            btn.remove(img)
            vbox.pack_start(img, False, False, 0)
            domain = _domain_label(shortcut.get("path", ""))
            if domain:
                lbl = Gtk.Label(label=domain)
                lbl.set_opacity(0.65)
                lbl.override_font(_pango_desc("7"))
                vbox.pack_start(lbl, False, False, 0)
            btn.add(vbox)

        btn.connect("clicked", self._on_btn_clicked, shortcut)
        return btn

    def _make_builtin_widget(self, widget_id: str) -> Gtk.EventBox:
        """Create an inline built-in widget (clock / date / stopwatch)."""
        box = Gtk.EventBox()
        box.get_style_context().add_class("quickr-builtin")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        vbox.set_margin_start(6)
        vbox.set_margin_end(6)
        vbox.set_margin_top(4)
        vbox.set_margin_bottom(4)

        text_lbl = Gtk.Label(label=_builtin_text(widget_id, self._start_time))
        vbox.pack_start(text_lbl, False, False, 0)

        name_lbl = Gtk.Label(label=BUILTIN_LABELS.get(widget_id, widget_id))
        name_lbl.set_opacity(0.5)
        name_lbl.override_font(_pango_desc("7"))
        vbox.pack_start(name_lbl, False, False, 0)

        box.add(vbox)
        self._builtin_labels[widget_id] = text_lbl
        return box

    def _update_builtins(self) -> bool:
        """Refresh built-in widget labels every second."""
        for widget_id, lbl in self._builtin_labels.items():
            lbl.set_text(_builtin_text(widget_id, self._start_time))
        return True   # keep the timer alive

    # ------------------------------------------------------------------
    # AppImage update button
    # ------------------------------------------------------------------

    def _make_update_button(self) -> Gtk.Button:
        """Build the small 'Check for Updates' button shown in AppImage mode."""
        btn = Gtk.Button(label="⟳ Updates")
        btn.get_style_context().add_class("quickr-update-btn")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_focus_on_click(False)
        btn.set_tooltip_text(
            f"Quickr {upd.VERSION} – click to open Install Manager"
        )
        btn.connect("clicked", self._on_check_updates_clicked)
        return btn

    def _mark_update_available(self, latest_version: str) -> None:
        """Highlight the update button to indicate an available update."""
        if self._update_btn is None:
            return
        self._update_btn.set_label(f"↑ v{latest_version}")
        self._update_btn.set_tooltip_text(
            f"Update available: v{latest_version} (installed: v{upd.VERSION})\n"
            "Click to update"
        )
        ctx = self._update_btn.get_style_context()
        ctx.add_class("has-update")

    def _bg_check_for_updates(self) -> bool:
        """Background update check run once shortly after startup."""
        import threading

        def _worker():
            info = upd.check_for_updates()
            status = info.get("status")
            if status == "update_available":
                GLib.idle_add(self._on_update_found, info)
            elif status == "error":
                GLib.idle_add(self._on_update_check_error, info.get("message", "Unknown error"))

        threading.Thread(target=_worker, daemon=True).start()
        return False  # run only once

    def _on_update_found(self, info: dict) -> bool:
        """Called on the GTK main thread when an update is available."""
        self._update_info = info
        self._mark_update_available(info["latest"])
        return False

    def _on_update_check_error(self, message: str) -> bool:
        """Called on the GTK main thread when the update check fails."""
        if self._update_btn is None:
            return False
        self._update_btn.set_tooltip_text(
            f"Quickr {upd.VERSION} – update check failed\n{message}"
        )
        return False

    def _on_check_updates_clicked(self, _btn) -> None:
        """Open the Install Manager dialog."""
        from install_manager import InstallManagerDialog
        dlg = InstallManagerDialog(parent=self)
        dlg.run()
        # After the manager closes, reset the button state and re-run a
        # background check so the button badge stays in sync.
        self._update_info = None
        if self._update_btn is not None:
            self._update_btn.set_label("⟳ Updates")
            ctx = self._update_btn.get_style_context()
            ctx.remove_class("has-update")
            self._update_btn.set_tooltip_text(
                f"Quickr {upd.VERSION} – click to open Install Manager"
            )
        if upd.is_appimage():
            GLib.timeout_add_seconds(1, self._bg_check_for_updates)

    # ------------------------------------------------------------------
    # Mini console
    # ------------------------------------------------------------------

    def _toggle_console(self):
        """Show or hide the mini console panel and resize the bar accordingly."""
        self._console_visible = not self._console_visible
        if self._console_visible:
            self._console_panel.show()
            self._console_btn.get_style_context().add_class("active")
            GLib.idle_add(self._console_entry.grab_focus)
        else:
            self._console_panel.hide()
            self._console_btn.get_style_context().remove_class("active")
        GLib.idle_add(self._reposition_for_console)

    def _reposition_for_console(self) -> bool:
        bar_height = self._settings.get("bar_height", 48)
        if self._console_visible:
            bar_height += CONSOLE_EXTRA_HEIGHT
        self._position(bar_height)
        return False

    def _on_console_cmd(self, _widget=None):
        """Run the command typed in the console entry and append output."""
        import shlex
        cmd = self._console_entry.get_text().strip()
        if not cmd:
            return
        self._console_entry.set_text("")

        end_iter = self._console_buf.get_end_iter()
        self._console_buf.insert(end_iter, f"$ {cmd}\n")

        try:
            args = shlex.split(cmd)
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout or ""
            if result.stderr:
                output += result.stderr
        except subprocess.TimeoutExpired:
            output = "(command timed out after 10 seconds)\n"
        except Exception as exc:
            output = f"(error: {exc})\n"

        if output and not output.endswith("\n"):
            output += "\n"
        end_iter = self._console_buf.get_end_iter()
        self._console_buf.insert(end_iter, output if output else "(no output)\n")

        # Scroll to end
        adj = self._console_view.get_vadjustment()
        if adj:
            GLib.idle_add(lambda: adj.set_value(adj.get_upper()))

    def _on_key_press(self, _widget, event):
        """Handle global bar keyboard shortcuts."""
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and event.keyval == Gdk.KEY_grave:
            self._toggle_console()
            return True
        return False

    def _on_btn_clicked(self, _btn, shortcut):
        try:
            _open_shortcut(shortcut)
        except Exception as e:
            _show_error(self, str(e))

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _position(self, bar_height: int = None):
        if bar_height is None:
            bar_height = self._settings.get("bar_height", 48)
            if self._console_visible:
                bar_height += CONSOLE_EXTRA_HEIGHT
        screen = Gdk.Screen.get_default()
        mon    = screen.get_primary_monitor()
        geom   = screen.get_monitor_geometry(mon)

        self._btn_box.show_all()
        self._btn_box.queue_resize()
        nat_w = self._btn_box.get_preferred_width()[1]
        nat_w += 24   # margins
        # console toggle button
        nat_w += self._console_btn.get_preferred_width()[1] + 12

        bar_w = max(nat_w, 120)
        bar_x = geom.x + (geom.width - bar_w) // 2
        bar_y = geom.y  # top of the screen – notch style

        self.set_default_size(bar_w, bar_height)
        self.resize(bar_w, bar_height)
        self.move(bar_x, bar_y)

    # ------------------------------------------------------------------
    # Public: reload
    # ------------------------------------------------------------------

    def reload(self):
        self._settings = cfg.get_settings()
        self.reload_style()
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


def _show_info(parent, title: str, msg: str):
    dlg = Gtk.MessageDialog(
        transient_for=parent,
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.CLOSE,
        text=title,
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
