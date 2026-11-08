#!/usr/bin/env python3
"""Isle – Windows Dynamic Island companion for Quickr.

Uses PySide6 (not GTK). Quickr's Windows exe excludes gi and never draws;
Isle is the Windows-native shell for media session + toast UI.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def read_version() -> str:
    """Resolve VERSION from source tree or PyInstaller bundle."""
    candidates = [
        _ROOT / "VERSION",
        Path(getattr(sys, "_MEIPASS", _ROOT)) / "VERSION",
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            continue
    return "0.0.0"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    version = read_version()
    logging.getLogger("isle").info("Isle %s starting", version)
    if sys.platform != "win32":
        logging.getLogger("isle").warning(
            "Isle targets Windows (winsdk media session). Continuing anyway."
        )
    from island import run

    return run(version=version)


if __name__ == "__main__":
    raise SystemExit(main())
