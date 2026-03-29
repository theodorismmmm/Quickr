#!/usr/bin/env python3
"""Quickr – configuration manager.

Shortcuts are stored in ~/.config/quickr/shortcuts.json.
Each entry has the shape::

    {
        "id":   "unique-string",
        "type": "app" | "file" | "folder" | "url",
        "name": "Human-readable label",
        "path": "/absolute/path  or  https://url"
    }
"""

import json
import uuid
from pathlib import Path

CONFIG_DIR  = Path.home() / ".config" / "quickr"
CONFIG_FILE = CONFIG_DIR / "shortcuts.json"

SHORTCUT_TYPES = ("app", "file", "folder", "url")


def _ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({"shortcuts": []}, indent=2))


def load() -> dict:
    _ensure_config()
    try:
        data = json.loads(CONFIG_FILE.read_text())
        if "shortcuts" not in data:
            data["shortcuts"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"shortcuts": []}


def save(data: dict) -> None:
    _ensure_config()
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def add_shortcut(name: str, shortcut_type: str, path: str, sudo: bool = False) -> dict:
    if shortcut_type not in SHORTCUT_TYPES:
        raise ValueError(f"Invalid type '{shortcut_type}'. Must be one of {SHORTCUT_TYPES}")
    data = load()
    entry = {
        "id":   str(uuid.uuid4()),
        "type": shortcut_type,
        "name": name.strip(),
        "path": path.strip(),
        "sudo": bool(sudo),
    }
    data["shortcuts"].append(entry)
    save(data)
    return entry


def remove_shortcut(shortcut_id: str) -> bool:
    data = load()
    before = len(data["shortcuts"])
    data["shortcuts"] = [s for s in data["shortcuts"] if s.get("id") != shortcut_id]
    if len(data["shortcuts"]) < before:
        save(data)
        return True
    return False


def update_shortcut(shortcut_id: str, name: str, shortcut_type: str, path: str, sudo: bool = False) -> bool:
    if shortcut_type not in SHORTCUT_TYPES:
        raise ValueError(f"Invalid type '{shortcut_type}'.")
    data = load()
    for s in data["shortcuts"]:
        if s.get("id") == shortcut_id:
            s["name"] = name.strip()
            s["type"] = shortcut_type
            s["path"] = path.strip()
            s["sudo"] = bool(sudo)
            save(data)
            return True
    return False


def get_shortcuts() -> list:
    return load().get("shortcuts", [])


# ---------------------------------------------------------------------------
# Settings (transparency, icon size, bar height, built-in widgets)
# ---------------------------------------------------------------------------

SETTINGS_FILE = CONFIG_DIR / "settings.json"
BUILTIN_WIDGET_IDS = ("clock", "date", "stopwatch")

# Supported browser choices for opening URL shortcuts.
# "default" means use the system default browser (xdg-open / webbrowser).
BROWSER_OPTIONS = ("default", "chrome", "chromium", "firefox")

DEFAULT_SETTINGS: dict = {
    "transparency": 0.96,
    "icon_size": 28,
    "bar_height": 48,
    "show_on_startup": True,
    "builtin_widgets": [],
    "browser": "default",
}


def get_settings() -> dict:
    """Load application settings, merging with defaults for any missing keys."""
    _ensure_config()
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        result = dict(DEFAULT_SETTINGS)
        result.update(data)
        return result
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    """Persist settings to disk."""
    _ensure_config()
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
