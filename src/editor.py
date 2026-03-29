#!/usr/bin/env python3
"""Quickr – shortcut editor window.

Open via terminal:
    quickr editor
"""

import datetime
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

_SRC = Path(__file__).parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import config as cfg
import icons as ico

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

EDITOR_CSS = b"""
/* ---- Quickr Editor ---- */
window {
    background-color: #161616;
    color: #e0e0e0;
}

.qe-header {
    background-color: #1c1c1c;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 14px 20px;
}

.qe-title {
    font-size: 17px;
    font-weight: 600;
    color: #f0f0f0;
    letter-spacing: 0.5px;
}

.qe-subtitle {
    font-size: 11px;
    color: #888888;
    margin-top: 2px;
}

.qe-list-area {
    background-color: #1a1a1a;
    border-right: 1px solid rgba(255,255,255,0.06);
}

.qe-row {
    background-color: transparent;
    padding: 6px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}

.qe-row:selected {
    background-color: rgba(100,180,255,0.12);
}

.qe-row-name {
    font-size: 13px;
    color: #e0e0e0;
}

.qe-row-meta {
    font-size: 10px;
    color: #666666;
}

.qe-type-badge {
    font-size: 9px;
    color: #aaaaaa;
    background-color: rgba(255,255,255,0.08);
    border-radius: 3px;
    padding: 1px 5px;
    margin-left: 6px;
}

.qe-form-area {
    background-color: #161616;
    padding: 20px 24px;
}

.qe-settings-area {
    background-color: #161616;
    padding: 20px 24px;
}

.qe-builtins-area {
    background-color: #161616;
    padding: 20px 24px;
}

.qe-label {
    font-size: 11px;
    color: #888888;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 3px;
}

.qe-section-title {
    font-size: 13px;
    font-weight: 600;
    color: #c0c0c0;
    margin-bottom: 4px;
}

.qe-section-desc {
    font-size: 11px;
    color: #666666;
    margin-bottom: 12px;
}

.qe-preview-bar {
    background-color: rgba(18,18,18,0.92);
    border-top: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
    padding: 4px 10px;
}

.qe-preview-label {
    font-size: 10px;
    color: #555555;
    margin-right: 8px;
}

entry {
    background-color: #222222;
    color: #e0e0e0;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 5px;
    padding: 6px 10px;
    caret-color: #64b4ff;
}

entry:focus {
    border-color: rgba(100,180,255,0.45);
}

combobox button {
    background-color: #222222;
    color: #e0e0e0;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 5px;
    padding: 5px 10px;
}

.qe-btn-primary {
    background: linear-gradient(180deg,#3d8bef,#2673d4);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 12px;
}

.qe-btn-primary:hover {
    background: linear-gradient(180deg,#5a9df0,#3580e0);
}

.qe-btn-danger {
    background: transparent;
    color: #e05555;
    border: 1px solid rgba(220,80,80,0.35);
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
}

.qe-btn-danger:hover {
    background-color: rgba(220,80,80,0.12);
}

.qe-btn-secondary {
    background: transparent;
    color: #aaaaaa;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
}

.qe-btn-secondary:hover {
    background-color: rgba(255,255,255,0.07);
    color: #e0e0e0;
}

.qe-divider {
    background-color: rgba(255,255,255,0.07);
    min-height: 1px;
}

scale trough {
    background-color: #333333;
    border-radius: 3px;
    min-height: 4px;
}

scale highlight {
    background-color: #3d8bef;
    border-radius: 3px;
}
"""

ICON_SIZE = 24
WINDOW_W  = 820
WINDOW_H  = 580

# Human-readable info for each built-in widget
BUILTIN_INFO = {
    "clock":     ("🕐  Animated Clock",  "Displays the current time (HH:MM:SS), updated every second."),
    "date":      ("📅  Current Date",    "Shows today's date (DD Mon YYYY)."),
    "stopwatch": ("⏱  Time Elapsed",    "Counts up from when Quickr was started."),
}


# ---------------------------------------------------------------------------
# Editor window
# ---------------------------------------------------------------------------

class QuickrEditor(Gtk.Window):
    def __init__(self):
        super().__init__()
        self._selected_id: str | None = None
        self._apply_style()
        self._build_window()
        self._populate_list()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _apply_style(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(EDITOR_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_window(self):
        self.set_title("Quickr Editor")
        self.set_default_size(WINDOW_W, WINDOW_H)
        self.set_resizable(True)
        self.connect("destroy", Gtk.main_quit)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        root.pack_start(self._make_header(), False, False, 0)

        # Notebook for tabs
        self._notebook = Gtk.Notebook()
        self._notebook.set_tab_pos(Gtk.PositionType.TOP)
        root.pack_start(self._notebook, True, True, 0)

        self._notebook.append_page(
            self._make_tab_shortcuts(),
            Gtk.Label(label="  Shortcuts  "),
        )
        self._notebook.append_page(
            self._make_tab_builtins(),
            Gtk.Label(label="  Built-in Widgets  "),
        )
        self._notebook.append_page(
            self._make_tab_settings(),
            Gtk.Label(label="  Settings  "),
        )

        # Live bar preview strip (always visible at the bottom)
        root.pack_start(self._make_preview(), False, False, 0)

    def _make_header(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.get_style_context().add_class("qe-header")

        title = Gtk.Label(label="Quickr Editor")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("qe-title")
        box.pack_start(title, False, False, 0)

        sub = Gtk.Label(label="Manage your minibar shortcuts and settings")
        sub.set_halign(Gtk.Align.START)
        sub.get_style_context().add_class("qe-subtitle")
        box.pack_start(sub, False, False, 2)

        return box

    # ------------------------------------------------------------------
    # Tab 1 – Shortcuts (existing functionality)
    # ------------------------------------------------------------------

    def _make_tab_shortcuts(self) -> Gtk.Widget:
        pane = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        pane.pack_start(self._make_list_panel(), False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.get_style_context().add_class("qe-divider")
        pane.pack_start(sep, False, False, 0)

        pane.pack_start(self._make_form_panel(), True, True, 0)
        return pane

    def _make_list_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(260, -1)
        box.get_style_context().add_class("qe-list-area")

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._list_store = Gtk.ListStore(str, str, str, str, GdkPixbuf.Pixbuf)
        # columns: id, name, type, path, icon

        self._tree = Gtk.TreeView(model=self._list_store)
        self._tree.set_headers_visible(False)
        self._tree.set_activate_on_single_click(True)

        r_ico = Gtk.CellRendererPixbuf()
        col_ico = Gtk.TreeViewColumn("", r_ico, pixbuf=4)
        col_ico.set_fixed_width(36)
        self._tree.append_column(col_ico)

        r_txt = Gtk.CellRendererText()
        r_txt.set_property("ellipsize", 3)   # PANGO_ELLIPSIZE_END
        col_txt = Gtk.TreeViewColumn("Name", r_txt, text=1)
        self._tree.append_column(col_txt)

        self._tree.connect("cursor-changed", self._on_row_selected)
        scroll.add(self._tree)
        box.pack_start(scroll, True, True, 0)

        add_btn = Gtk.Button(label="+ New Shortcut")
        add_btn.get_style_context().add_class("qe-btn-secondary")
        add_btn.set_margin_start(10)
        add_btn.set_margin_end(10)
        add_btn.set_margin_top(8)
        add_btn.set_margin_bottom(8)
        add_btn.connect("clicked", self._on_new_clicked)
        box.pack_start(add_btn, False, False, 0)

        return box

    def _make_form_panel(self) -> Gtk.Widget:
        self._form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._form_box.get_style_context().add_class("qe-form-area")
        self._show_form_empty()
        return self._form_box

    def _clear_form(self):
        for child in self._form_box.get_children():
            self._form_box.remove(child)

    def _show_form_empty(self):
        self._clear_form()
        lbl = Gtk.Label(label='Select a shortcut to edit\nor click "+ New Shortcut"')
        lbl.set_opacity(0.35)
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_valign(Gtk.Align.CENTER)
        lbl.set_vexpand(True)
        self._form_box.pack_start(lbl, True, True, 0)
        self._form_box.show_all()

    def _build_form(self, shortcut: dict | None = None):
        """Build the add/edit form. *shortcut* = None means "new"."""
        self._clear_form()

        editing = shortcut is not None
        title_text = "Edit Shortcut" if editing else "New Shortcut"

        title = Gtk.Label(label=title_text)
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("qe-title")
        title.set_margin_bottom(20)
        self._form_box.pack_start(title, False, False, 0)

        # Preview icon
        if editing:
            icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            pixbuf = ico.get_icon(shortcut, 40) or ico.get_placeholder_pixbuf(40)
            self._preview_icon = Gtk.Image.new_from_pixbuf(pixbuf)
            icon_box.pack_start(self._preview_icon, False, False, 0)
            icon_label = Gtk.Label(label=shortcut.get("name", ""))
            icon_label.set_halign(Gtk.Align.START)
            icon_box.pack_start(icon_label, False, False, 0)
            self._form_box.pack_start(icon_box, False, False, 0)
            self._spacer(12)

        # Name
        self._form_box.pack_start(self._field_label("NAME"), False, False, 0)
        self._ent_name = Gtk.Entry()
        self._ent_name.set_placeholder_text("e.g. Firefox, Documents, …")
        if editing:
            self._ent_name.set_text(shortcut.get("name", ""))
        self._form_box.pack_start(self._ent_name, False, False, 0)
        self._spacer(8)

        # Type
        self._form_box.pack_start(self._field_label("TYPE"), False, False, 0)
        self._type_combo = Gtk.ComboBoxText()
        for t in cfg.SHORTCUT_TYPES:
            self._type_combo.append(t, t.capitalize())
        if editing:
            self._type_combo.set_active_id(shortcut.get("type", "app"))
        else:
            self._type_combo.set_active_id("app")
        self._form_box.pack_start(self._type_combo, False, False, 0)
        self._spacer(8)

        # Path / URL row
        path_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        path_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        path_col.set_hexpand(True)
        path_col.pack_start(self._field_label("PATH / URL"), False, False, 0)
        self._ent_path = Gtk.Entry()
        self._ent_path.set_placeholder_text("/usr/bin/app   or   https://example.com")
        self._ent_path.set_hexpand(True)
        if editing:
            self._ent_path.set_text(shortcut.get("path", ""))
        path_col.pack_start(self._ent_path, False, False, 0)
        path_row.pack_start(path_col, True, True, 0)

        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.get_style_context().add_class("qe-btn-secondary")
        browse_btn.set_valign(Gtk.Align.END)
        browse_btn.connect("clicked", self._on_browse_clicked)
        path_row.pack_start(browse_btn, False, False, 0)
        self._form_box.pack_start(path_row, False, False, 0)

        self._spacer(8)

        # Sudo mode (only relevant for app shortcuts)
        sudo_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._sudo_check = Gtk.CheckButton(label="Run with elevated privileges (sudo/pkexec)")
        self._sudo_check.set_tooltip_text(
            "Use pkexec to launch this shortcut with administrator privileges.\n"
            "Only applies to app-type shortcuts."
        )
        if editing:
            self._sudo_check.set_active(bool(shortcut.get("sudo", False)))
        sudo_row.pack_start(self._sudo_check, False, False, 0)
        self._form_box.pack_start(sudo_row, False, False, 0)

        self._spacer(16)

        # Action buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        save_btn = Gtk.Button(label="Save")
        save_btn.get_style_context().add_class("qe-btn-primary")
        save_btn.connect("clicked", self._on_save_clicked, shortcut)
        btn_row.pack_start(save_btn, False, False, 0)

        if editing:
            del_btn = Gtk.Button(label="Delete")
            del_btn.get_style_context().add_class("qe-btn-danger")
            del_btn.connect("clicked", self._on_delete_clicked, shortcut)
            btn_row.pack_start(del_btn, False, False, 0)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.get_style_context().add_class("qe-btn-secondary")
        cancel_btn.connect("clicked", lambda _b: self._show_form_empty())
        btn_row.pack_end(cancel_btn, False, False, 0)

        self._form_box.pack_start(btn_row, False, False, 0)
        self._form_box.show_all()

    def _field_label(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("qe-label")
        return lbl

    def _spacer(self, px: int):
        box = Gtk.Box()
        box.set_size_request(-1, px)
        self._form_box.pack_start(box, False, False, 0)

    # ------------------------------------------------------------------
    # Tab 2 – Built-in Widgets
    # ------------------------------------------------------------------

    def _make_tab_builtins(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.get_style_context().add_class("qe-builtins-area")
        outer.set_margin_start(24)
        outer.set_margin_end(24)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)

        heading = Gtk.Label(label="Built-in Widgets")
        heading.set_halign(Gtk.Align.START)
        heading.get_style_context().add_class("qe-title")
        heading.set_margin_bottom(4)
        outer.pack_start(heading, False, False, 0)

        desc = Gtk.Label(label="Toggle widgets that appear in the bar alongside your shortcuts.")
        desc.set_halign(Gtk.Align.START)
        desc.get_style_context().add_class("qe-subtitle")
        desc.set_margin_bottom(20)
        outer.pack_start(desc, False, False, 0)

        settings = cfg.get_settings()
        enabled = set(settings.get("builtin_widgets", []))

        self._builtin_switches: dict = {}
        for widget_id, (label, description) in BUILTIN_INFO.items():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_bottom(16)

            # Text column
            text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text_col.set_hexpand(True)

            name_lbl = Gtk.Label(label=label)
            name_lbl.set_halign(Gtk.Align.START)
            name_lbl.get_style_context().add_class("qe-section-title")
            text_col.pack_start(name_lbl, False, False, 0)

            desc_lbl = Gtk.Label(label=description)
            desc_lbl.set_halign(Gtk.Align.START)
            desc_lbl.get_style_context().add_class("qe-section-desc")
            text_col.pack_start(desc_lbl, False, False, 0)

            row.pack_start(text_col, True, True, 0)

            switch = Gtk.Switch()
            switch.set_active(widget_id in enabled)
            switch.set_valign(Gtk.Align.CENTER)
            switch.connect("state-set", self._on_builtin_toggled, widget_id)
            row.pack_start(switch, False, False, 0)

            self._builtin_switches[widget_id] = switch
            outer.pack_start(row, False, False, 0)

            sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            sep.set_opacity(0.15)
            outer.pack_start(sep, False, False, 0)
            self._spacer_in(outer, 8)

        return outer

    # ------------------------------------------------------------------
    # Tab 3 – Settings
    # ------------------------------------------------------------------

    def _make_tab_settings(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.get_style_context().add_class("qe-settings-area")
        outer.set_margin_start(24)
        outer.set_margin_end(24)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)

        heading = Gtk.Label(label="Bar Settings")
        heading.set_halign(Gtk.Align.START)
        heading.get_style_context().add_class("qe-title")
        heading.set_margin_bottom(20)
        outer.pack_start(heading, False, False, 0)

        settings = cfg.get_settings()

        # -- Transparency --
        outer.pack_start(self._settings_label("BACKGROUND TRANSPARENCY"), False, False, 0)
        outer.pack_start(self._settings_sublabel(
            "Controls how opaque the bar background is (0 = fully transparent, 1 = solid)"
        ), False, False, 0)

        transp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._transp_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01
        )
        self._transp_scale.set_value(settings.get("transparency", 0.96))
        self._transp_scale.set_hexpand(True)
        self._transp_scale.set_draw_value(True)
        self._transp_scale.set_digits(2)
        transp_row.pack_start(self._transp_scale, True, True, 0)
        outer.pack_start(transp_row, False, False, 0)
        self._spacer_in(outer, 20)

        # -- Icon size --
        outer.pack_start(self._settings_label("ICON SIZE (px)"), False, False, 0)
        outer.pack_start(self._settings_sublabel(
            "Size of shortcut icons in the bar (16–56 px)"
        ), False, False, 0)

        self._icon_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 16, 56, 2
        )
        self._icon_scale.set_value(settings.get("icon_size", 28))
        self._icon_scale.set_hexpand(True)
        self._icon_scale.set_draw_value(True)
        self._icon_scale.set_digits(0)
        outer.pack_start(self._icon_scale, False, False, 0)
        self._spacer_in(outer, 20)

        # -- Bar height --
        outer.pack_start(self._settings_label("BAR HEIGHT (px)"), False, False, 0)
        outer.pack_start(self._settings_sublabel(
            "Height of the bar panel (32–80 px)"
        ), False, False, 0)

        self._height_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 32, 80, 2
        )
        self._height_scale.set_value(settings.get("bar_height", 48))
        self._height_scale.set_hexpand(True)
        self._height_scale.set_draw_value(True)
        self._height_scale.set_digits(0)
        outer.pack_start(self._height_scale, False, False, 0)
        self._spacer_in(outer, 20)

        # -- Show on startup --
        startup_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        startup_lbl_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        startup_lbl_col.set_hexpand(True)
        startup_lbl_col.pack_start(self._settings_label("SHOW ON STARTUP"), False, False, 0)
        startup_lbl_col.pack_start(
            self._settings_sublabel("Show the bar automatically when Quickr starts"),
            False, False, 0,
        )
        startup_row.pack_start(startup_lbl_col, True, True, 0)
        self._startup_switch = Gtk.Switch()
        self._startup_switch.set_active(settings.get("show_on_startup", True))
        self._startup_switch.set_valign(Gtk.Align.CENTER)
        startup_row.pack_start(self._startup_switch, False, False, 0)
        outer.pack_start(startup_row, False, False, 0)
        self._spacer_in(outer, 20)

        # -- Browser --
        outer.pack_start(self._settings_label("URL BROWSER"), False, False, 0)
        outer.pack_start(self._settings_sublabel(
            "Browser used to open URL shortcuts (falls back to system default if not found)"
        ), False, False, 0)

        self._browser_combo = Gtk.ComboBoxText()
        for opt in cfg.BROWSER_OPTIONS:
            self._browser_combo.append(opt, opt.capitalize() if opt != "default" else "System Default")
        self._browser_combo.set_active_id(settings.get("browser", "default") or "default")
        outer.pack_start(self._browser_combo, False, False, 0)
        self._spacer_in(outer, 28)

        # Apply button
        apply_btn = Gtk.Button(label="Apply Settings")
        apply_btn.get_style_context().add_class("qe-btn-primary")
        apply_btn.set_halign(Gtk.Align.START)
        apply_btn.connect("clicked", self._on_apply_settings)
        outer.pack_start(apply_btn, False, False, 0)

        return outer

    def _settings_label(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("qe-label")
        return lbl

    def _settings_sublabel(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("qe-section-desc")
        lbl.set_margin_bottom(6)
        return lbl

    def _spacer_in(self, parent: Gtk.Box, px: int):
        box = Gtk.Box()
        box.set_size_request(-1, px)
        parent.pack_start(box, False, False, 0)

    # ------------------------------------------------------------------
    # Live bar preview
    # ------------------------------------------------------------------

    def _make_preview(self) -> Gtk.Widget:
        """Build the always-visible preview bar at the bottom of the editor."""
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        top_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        top_sep.set_opacity(0.15)
        wrapper.pack_start(top_sep, False, False, 0)

        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        strip.set_margin_start(12)
        strip.set_margin_end(12)
        strip.set_margin_top(6)
        strip.set_margin_bottom(6)

        preview_lbl = Gtk.Label(label="Preview:")
        preview_lbl.get_style_context().add_class("qe-preview-label")
        strip.pack_start(preview_lbl, False, False, 0)

        self._preview_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
        )
        self._preview_box.get_style_context().add_class("qe-preview-bar")
        self._preview_box.set_hexpand(True)
        strip.pack_start(self._preview_box, True, True, 0)

        wrapper.pack_start(strip, False, False, 0)
        self._refresh_preview()
        return wrapper

    def _refresh_preview(self):
        """Rebuild the preview strip to match current shortcuts + enabled widgets."""
        for child in self._preview_box.get_children():
            self._preview_box.remove(child)

        shortcuts = cfg.get_shortcuts()
        settings  = cfg.get_settings()
        enabled   = settings.get("builtin_widgets", [])

        if not shortcuts and not enabled:
            empty = Gtk.Label(label="(no shortcuts yet)")
            empty.set_opacity(0.4)
            self._preview_box.pack_start(empty, False, False, 0)
        else:
            for s in shortcuts:
                pb = ico.get_icon(s, 18) or ico.get_placeholder_pixbuf(18)
                btn = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                btn.set_margin_start(2)
                btn.set_margin_end(2)
                img = Gtk.Image.new_from_pixbuf(pb)
                btn.pack_start(img, False, False, 0)
                _raw = s.get("name", "")
                _display = _raw[:8] + "…" if len(_raw) > 8 else _raw
                name_lbl = Gtk.Label(label=_display)
                name_lbl.set_opacity(0.6)
                name_lbl.override_font(_pango_desc("7"))
                btn.pack_start(name_lbl, False, False, 0)
                self._preview_box.pack_start(btn, False, False, 0)

            for widget_id in enabled:
                now = datetime.datetime.now()
                if widget_id == "clock":
                    txt = now.strftime("%H:%M")
                elif widget_id == "date":
                    txt = now.strftime("%d %b")
                else:
                    txt = "00:00"
                lbl = Gtk.Label(label=txt)
                lbl.set_opacity(0.8)
                lbl.override_font(_pango_desc("8"))
                lbl.set_margin_start(4)
                lbl.set_margin_end(4)
                self._preview_box.pack_start(lbl, False, False, 0)

        self._preview_box.show_all()

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _populate_list(self):
        self._list_store.clear()
        for s in cfg.get_shortcuts():
            pixbuf = ico.get_icon(s, ICON_SIZE) or ico.get_placeholder_pixbuf(ICON_SIZE)
            self._list_store.append([
                s.get("id", ""),
                s.get("name", "(unnamed)"),
                s.get("type", ""),
                s.get("path", ""),
                pixbuf,
            ])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_row_selected(self, tree):
        model, it = tree.get_selection().get_selected()
        if it is None:
            return
        sid = model[it][0]
        shortcuts = cfg.get_shortcuts()
        match = next((s for s in shortcuts if s.get("id") == sid), None)
        if match:
            self._selected_id = sid
            self._build_form(match)

    def _on_new_clicked(self, _btn):
        self._selected_id = None
        self._tree.get_selection().unselect_all()
        self._build_form(None)

    def _on_save_clicked(self, _btn, existing: dict | None):
        name  = self._ent_name.get_text().strip()
        stype = self._type_combo.get_active_id()
        path  = self._ent_path.get_text().strip()
        sudo  = self._sudo_check.get_active()

        if not name:
            self._shake_entry(self._ent_name)
            return
        if not path:
            self._shake_entry(self._ent_path)
            return

        try:
            if existing:
                cfg.update_shortcut(existing["id"], name, stype, path, sudo=sudo)
            else:
                cfg.add_shortcut(name, stype, path, sudo=sudo)
        except ValueError as exc:
            self._error(str(exc))
            return

        self._populate_list()
        self._show_form_empty()
        self._refresh_preview()

    def _on_delete_clicked(self, _btn, shortcut: dict):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f'Delete "{shortcut.get("name")}"?',
        )
        dlg.format_secondary_text("This cannot be undone.")
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            cfg.remove_shortcut(shortcut["id"])
            self._populate_list()
            self._show_form_empty()
            self._refresh_preview()

    def _on_browse_clicked(self, _btn):
        stype = self._type_combo.get_active_id() or "file"
        if stype == "folder":
            action = Gtk.FileChooserAction.SELECT_FOLDER
            title  = "Select Folder"
        elif stype == "app":
            action = Gtk.FileChooserAction.OPEN
            title  = "Select Application"
        else:
            action = Gtk.FileChooserAction.OPEN
            title  = "Select File"

        dlg = Gtk.FileChooserDialog(
            title=title,
            parent=self,
            action=action,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,   Gtk.ResponseType.OK,
        )
        if dlg.run() == Gtk.ResponseType.OK:
            self._ent_path.set_text(dlg.get_filename())
        dlg.destroy()

    def _on_builtin_toggled(self, switch, state, widget_id: str):
        """Save the updated enabled-widget list when a toggle changes."""
        settings = cfg.get_settings()
        enabled  = list(settings.get("builtin_widgets", []))
        if state:
            if widget_id not in enabled:
                enabled.append(widget_id)
        else:
            enabled = [w for w in enabled if w != widget_id]
        settings["builtin_widgets"] = enabled
        cfg.save_settings(settings)
        self._refresh_preview()

    def _on_apply_settings(self, _btn):
        """Persist slider values to settings."""
        settings = cfg.get_settings()
        settings["transparency"]   = round(self._transp_scale.get_value(), 2)
        settings["icon_size"]      = int(self._icon_scale.get_value())
        settings["bar_height"]     = int(self._height_scale.get_value())
        settings["show_on_startup"] = self._startup_switch.get_active()
        settings["browser"]        = self._browser_combo.get_active_id() or "default"
        cfg.save_settings(settings)

        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Settings saved",
        )
        dlg.format_secondary_text(
            "Restart the bar (click the tray icon) to apply transparency and size changes."
        )
        dlg.run()
        dlg.destroy()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _shake_entry(self, entry: Gtk.Entry):
        entry.get_style_context().add_class("error")

        def _remove_class():
            entry.get_style_context().remove_class("error")
            return False

        GLib.timeout_add(800, _remove_class)

    def _error(self, msg: str):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Error",
        )
        dlg.format_secondary_text(msg)
        dlg.run()
        dlg.destroy()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _pango_desc(size: str):
    from gi.repository import Pango
    return Pango.font_description_from_string(f"Sans {size}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    win = QuickrEditor()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
