#!/usr/bin/env python3
"""Quickr – icon resolution helpers."""

import os
import subprocess
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GdkPixbuf, Gio


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pixbuf_from_theme(icon_name: str, size: int) -> "GdkPixbuf.Pixbuf | None":
    theme = Gtk.IconTheme.get_default()
    try:
        return theme.load_icon(icon_name, size, Gtk.IconLookupFlags.FORCE_SIZE)
    except Exception:
        return None


def _pixbuf_from_file(path: str, size: int) -> "GdkPixbuf.Pixbuf | None":
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
    except Exception:
        return None


def _icon_from_desktop(desktop_path: str, size: int) -> "GdkPixbuf.Pixbuf | None":
    """Parse a .desktop file and return an icon pixbuf."""
    icon_name = None
    try:
        with open(desktop_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("Icon="):
                    icon_name = line.strip()[5:]
                    break
    except OSError:
        return None

    if not icon_name:
        return None

    # Absolute path?
    if os.path.isabs(icon_name) and os.path.isfile(icon_name):
        return _pixbuf_from_file(icon_name, size)

    # Try theme lookup
    pb = _pixbuf_from_theme(icon_name, size)
    if pb:
        return pb

    # Try common icon directories
    for base in (
        "/usr/share/icons",
        "/usr/share/pixmaps",
        str(Path.home() / ".local/share/icons"),
    ):
        for ext in ("png", "svg", "xpm"):
            candidate = Path(base) / f"{icon_name}.{ext}"
            if candidate.is_file():
                pb = _pixbuf_from_file(str(candidate), size)
                if pb:
                    return pb

    return None


def _find_desktop_file(app_name: str) -> "str | None":
    """Search standard locations for a .desktop file matching *app_name*."""
    search_dirs = [
        Path.home() / ".local/share/applications",
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
    ]
    needle = app_name.lower().replace(" ", "-")
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.desktop"):
            if needle in f.stem.lower():
                return str(f)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_icon(shortcut: dict, size: int = 32) -> "GdkPixbuf.Pixbuf | None":
    """Return an appropriately-sized Pixbuf for *shortcut*, or None."""
    stype = shortcut.get("type", "")
    path  = shortcut.get("path", "")
    name  = shortcut.get("name", "")

    if stype == "app":
        # path may be a .desktop file path or an app name
        if path.endswith(".desktop") and os.path.isfile(path):
            pb = _icon_from_desktop(path, size)
            if pb:
                return pb
        # Search by app name / path basename
        desktop = _find_desktop_file(name) or _find_desktop_file(os.path.basename(path))
        if desktop:
            pb = _icon_from_desktop(desktop, size)
            if pb:
                return pb
        # Fallback: try executable icon by name
        pb = _pixbuf_from_theme(name.lower(), size)
        if pb:
            return pb
        return _pixbuf_from_theme("application-x-executable", size)

    elif stype == "folder":
        return (
            _pixbuf_from_theme("folder", size)
            or _pixbuf_from_theme("inode-directory", size)
            or _pixbuf_from_theme("document-open", size)
        )

    elif stype == "file":
        # Try mime-type icon
        p = Path(path)
        if p.exists():
            content_type = Gio.content_type_guess(path, None)[0]
            gicon = Gio.content_type_get_icon(content_type)
            if isinstance(gicon, Gio.ThemedIcon):
                for n in gicon.get_names():
                    pb = _pixbuf_from_theme(n, size)
                    if pb:
                        return pb
        return (
            _pixbuf_from_theme("text-x-generic", size)
            or _pixbuf_from_theme("document", size)
        )

    elif stype == "url":
        return (
            _pixbuf_from_theme("applications-internet", size)
            or _pixbuf_from_theme("web-browser", size)
            or _pixbuf_from_theme("emblem-web", size)
            or _pixbuf_from_theme("network-workgroup", size)
        )

    return _pixbuf_from_theme("application-x-executable", size)


def get_placeholder_pixbuf(size: int = 32) -> GdkPixbuf.Pixbuf:
    """Return a blank pixbuf as a last-resort fallback."""
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, size, size)
    pb.fill(0x444444ff)
    return pb
