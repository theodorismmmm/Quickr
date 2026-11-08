#!/usr/bin/env python3
"""Isle – Windows Dynamic Island companion for Quickr.

Uses PySide6 (not GTK). Quickr's Windows exe excludes gi and never draws;
Isle is the Windows-native shell for media session + toast UI.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if sys.platform != "win32":
        logging.getLogger("isle").warning(
            "Isle targets Windows (winsdk media session). Continuing anyway."
        )
    from island import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
