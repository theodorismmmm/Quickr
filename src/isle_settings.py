"""Persistent Isle settings (YouTube Music + WhatsApp)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "Isle"
    return Path.home() / ".config" / "isle"


CONFIG_DIR = _config_dir()
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULTS: dict[str, Any] = {
    "youtube_music_enabled": True,
    "youtube_music_prefer": True,
    "youtube_music_url": "https://music.youtube.com",
    "whatsapp_toasts_enabled": True,
    "whatsapp_reply_enabled": True,
    "whatsapp_uri": "whatsapp:",
}


def load() -> dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        data = dict(DEFAULTS)
        save(data)
        return data
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    if isinstance(raw, dict):
        merged.update({k: raw[k] for k in DEFAULTS if k in raw})
    return merged


def save(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    out = dict(DEFAULTS)
    out.update({k: data.get(k, DEFAULTS[k]) for k in DEFAULTS})
    CONFIG_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")


def update(**kwargs: Any) -> dict[str, Any]:
    data = load()
    for key, value in kwargs.items():
        if key in DEFAULTS:
            data[key] = value
    save(data)
    return data
