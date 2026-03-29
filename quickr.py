#!/usr/bin/env python3
"""Quickr – main entry point.

Usage:
    quickr             Start the minibar
    quickr editor      Open the shortcut editor
    quickr update      Check for updates (and install if running as AppImage)
    quickr uninstall   Remove installed files (wrapper, desktop entries)
    quickr --help      Show help
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

    if args and args[0] == "update":
        _cmd_update()
    elif args and args[0] == "uninstall":
        _cmd_uninstall()
    elif args and args[0] == "editor":
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


def _cmd_update():
    """CLI handler for ``quickr update``."""
    from updater import (
        VERSION,
        RELEASES_PAGE,
        check_for_updates,
        do_appimage_update,
        is_appimage,
    )

    print(f"Quickr {VERSION} – checking for updates…")
    info = check_for_updates()

    if info is None:
        print("✓ Already up to date.")
        return

    print(
        f"  New version available: v{info['latest']}  (installed: v{info['current']})"
    )

    if is_appimage():
        if info.get("download_url"):
            reply = input("  Download and install now? [y/N] ").strip().lower()
            if reply == "y":
                print("  Downloading…", end="", flush=True)
                ok = do_appimage_update(info["download_url"])
                if ok:
                    print(" done!")
                    print("  Restart Quickr to use the new version.")
                else:
                    print(" failed.")
                    print(f"  Please download manually from:\n  {RELEASES_PAGE}")
        else:
            print(f"  Download the latest AppImage from:\n  {RELEASES_PAGE}")
    else:
        if info.get("download_url"):
            print(f"  AppImage download: {info['download_url']}")
        print(
            f"  Or update via git:\n"
            f"    cd <quickr-directory> && git pull && bash install.sh"
        )
        print(f"  Releases page: {RELEASES_PAGE}")


def _cmd_uninstall():
    """CLI handler for ``quickr uninstall``."""
    import shutil
    from pathlib import Path

    home = Path.home()
    targets = [
        home / ".local" / "bin" / "quickr",
        home / ".config" / "autostart" / "quickr.desktop",
        home / ".local" / "share" / "applications" / "quickr.desktop",
    ]

    removed_any = False
    for t in targets:
        if t.exists():
            t.unlink()
            print(f"  Removed: {t}")
            removed_any = True

    # Refresh the desktop database if applications entry was present
    apps_db = home / ".local" / "share" / "applications"
    if apps_db.is_dir():
        import subprocess
        subprocess.run(
            ["update-desktop-database", str(apps_db)],
            check=False,
            capture_output=True,
        )

    if not removed_any:
        print("Nothing to remove – no installed Quickr files found.")
        return

    # Optionally remove config
    config_dir = home / ".config" / "quickr"
    if config_dir.is_dir():
        try:
            reply = input(
                f"  Remove configuration directory ({config_dir})? [y/N] "
            ).strip().lower()
        except EOFError:
            reply = ""
        if reply == "y":
            shutil.rmtree(config_dir)
            print(f"  Removed: {config_dir}")

    print()
    print("Quickr has been uninstalled.")
    print("The source directory was NOT removed.")


if __name__ == "__main__":
    main()
