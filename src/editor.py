#!/usr/bin/env python3
"""Quickr – shortcut editor window.

Open via terminal:
    quickr editor
"""

import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf

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

.qe-label {
    font-size: 11px;
    color: #888888;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 3px;
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
"""

ICON_SIZE = 24
WINDOW_W  = 760
WINDOW_H  = 520


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

        pane = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(pane, True, True, 0)

        pane.pack_start(self._make_list_panel(), False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.get_style_context().add_class("qe-divider")
        pane.pack_start(sep, False, False, 0)

        pane.pack_start(self._make_form_panel(), True, True, 0)

    def _make_header(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.get_style_context().add_class("qe-header")

        title = Gtk.Label(label="Quickr Editor")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("qe-title")
        box.pack_start(title, False, False, 0)

        sub = Gtk.Label(label="Manage your minibar shortcuts")
        sub.set_halign(Gtk.Align.START)
        sub.get_style_context().add_class("qe-subtitle")
        box.pack_start(sub, False, False, 2)

        return box

    # ------------------------------------------------------------------
    # Left panel – shortcut list
    # ------------------------------------------------------------------

    def _make_list_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(260, -1)
        box.get_style_context().add_class("qe-list-area")

        # Scrolled list
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._list_store = Gtk.ListStore(str, str, str, str, GdkPixbuf.Pixbuf)
        # columns: id, name, type, path, icon

        self._tree = Gtk.TreeView(model=self._list_store)
        self._tree.set_headers_visible(False)
        self._tree.set_activate_on_single_click(True)

        # Icon column
        r_ico = Gtk.CellRendererPixbuf()
        col_ico = Gtk.TreeViewColumn("", r_ico, pixbuf=4)
        col_ico.set_fixed_width(36)
        self._tree.append_column(col_ico)

        # Name + meta column
        r_txt = Gtk.CellRendererText()
        r_txt.set_property("ellipsize", 3)  # PANGO_ELLIPSIZE_END
        col_txt = Gtk.TreeViewColumn("Name", r_txt, text=1)
        self._tree.append_column(col_txt)

        self._tree.connect("cursor-changed", self._on_row_selected)
        scroll.add(self._tree)
        box.pack_start(scroll, True, True, 0)

        # Add-new button at bottom of list
        add_btn = Gtk.Button(label="+ New Shortcut")
        add_btn.get_style_context().add_class("qe-btn-secondary")
        add_btn.set_margin_start(10)
        add_btn.set_margin_end(10)
        add_btn.set_margin_top(8)
        add_btn.set_margin_bottom(8)
        add_btn.connect("clicked", self._on_new_clicked)
        box.pack_start(add_btn, False, False, 0)

        return box

    # ------------------------------------------------------------------
    # Right panel – form
    # ------------------------------------------------------------------

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
        browse_btn.set_margin_bottom(0)
        browse_btn.connect("clicked", self._on_browse_clicked)
        path_row.pack_start(browse_btn, False, False, 0)
        self._form_box.pack_start(path_row, False, False, 0)

        self._spacer(24)

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

        if not name:
            self._shake_entry(self._ent_name)
            return
        if not path:
            self._shake_entry(self._ent_path)
            return

        try:
            if existing:
                cfg.update_shortcut(existing["id"], name, stype, path)
            else:
                cfg.add_shortcut(name, stype, path)
        except ValueError as exc:
            self._error(str(exc))
            return

        self._populate_list()
        self._show_form_empty()

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _shake_entry(self, entry: Gtk.Entry):
        entry.get_style_context().add_class("error")

        def _remove_class():
            entry.get_style_context().remove_class("error")
            return False

        from gi.repository import GLib
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
# Entry point
# ---------------------------------------------------------------------------

def main():
    win = QuickrEditor()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
