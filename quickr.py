#!/usr/bin/env python3
"""Quickr – main entry point.

Usage:
    quickr           Start the minibar
    quickr editor    Open the shortcut editor
    quickr --help    Show help
"""

import sys
from pathlib import Path

# Ensure the src directory is on the path regardless of cwd
_SCRIPT = Path(__file__).resolve()
_SRC    = _SCRIPT.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _usage():
    print(__doc__.strip())


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        _usage()
        return

    if args and args[0] == "editor":
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        from editor import main as editor_main
        editor_main()
    else:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        from bar import QuickrBar
        _bar = QuickrBar()
        Gtk.main()


if __name__ == "__main__":
    main()
