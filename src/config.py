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


def add_shortcut(name: str, shortcut_type: str, path: str) -> dict:
    if shortcut_type not in SHORTCUT_TYPES:
        raise ValueError(f"Invalid type '{shortcut_type}'. Must be one of {SHORTCUT_TYPES}")
    data = load()
    entry = {
        "id":   str(uuid.uuid4()),
        "type": shortcut_type,
        "name": name.strip(),
        "path": path.strip(),
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


def update_shortcut(shortcut_id: str, name: str, shortcut_type: str, path: str) -> bool:
    if shortcut_type not in SHORTCUT_TYPES:
        raise ValueError(f"Invalid type '{shortcut_type}'.")
    data = load()
    for s in data["shortcuts"]:
        if s.get("id") == shortcut_id:
            s["name"] = name.strip()
            s["type"] = shortcut_type
            s["path"] = path.strip()
            save(data)
            return True
    return False


def get_shortcuts() -> list:
    return load().get("shortcuts", [])
