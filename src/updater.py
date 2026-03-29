#!/usr/bin/env python3
"""Quickr – update checker and self-updater.

Public API
----------
VERSION          : str  – currently installed version string.
is_appimage()    : bool – True when running inside an AppImage.
check_for_updates() -> dict | None
    Returns {"current", "latest", "download_url"} when a newer release is
    available on GitHub, or None if already up to date / network is unreachable.
do_appimage_update(download_url) -> bool
    Downloads the new AppImage and replaces the running binary in-place.
    Only meaningful when is_appimage() is True.
"""

import json
import os
import stat
import tempfile
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Version – read from the VERSION file that lives next to quickr.py
# ---------------------------------------------------------------------------

_VERSION_FILE = Path(__file__).parent.parent / "VERSION"
VERSION: str = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "1.0.0"

# ---------------------------------------------------------------------------
# GitHub coordinates
# ---------------------------------------------------------------------------

GITHUB_REPO       = "theodorismmmm/Quickr"
RELEASES_API      = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_LIST_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
RELEASES_PAGE     = f"https://github.com/{GITHUB_REPO}/releases"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_appimage() -> bool:
    """Return True if the process is running inside an AppImage bundle."""
    return bool(os.environ.get("APPIMAGE"))


def _parse_version(v: str) -> tuple:
    """Parse a dotted version string into a tuple of ints for comparison."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except Exception:
        return (0,)


# ---------------------------------------------------------------------------
# Core public functions
# ---------------------------------------------------------------------------

def get_latest_release():
    """Query the GitHub Releases API and return (tag, appimage_url).

    Returns None when the network is unavailable or the request fails.
    The *appimage_url* component is None if no AppImage asset is found in the
    release, but a tag is still returned.
    """
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={"User-Agent": f"Quickr/{VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        tag = data.get("tag_name", "").lstrip("v")
        assets = data.get("assets", [])
        appimage_url = next(
            (
                a["browser_download_url"]
                for a in assets
                if a.get("name", "").endswith(".AppImage")
            ),
            None,
        )
        return tag, appimage_url
    except Exception:
        return None


def get_all_releases():
    """Query the GitHub Releases API and return a list of release dicts.

    Each dict contains:
        "version"      – version string (without leading 'v')
        "tag"          – original tag name
        "download_url" – AppImage asset URL, or None
        "is_current"   – True if this matches the installed VERSION
        "status"       – "current" | "newer" | "older"

    Returns an empty list when the network is unavailable or the request fails.
    """
    try:
        req = urllib.request.Request(
            RELEASES_LIST_API,
            headers={"User-Agent": f"Quickr/{VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        releases = []
        for entry in data:
            tag = entry.get("tag_name", "")
            version = tag.lstrip("v")
            assets = entry.get("assets", [])
            appimage_url = next(
                (
                    a["browser_download_url"]
                    for a in assets
                    if a.get("name", "").endswith(".AppImage")
                ),
                None,
            )
            parsed = _parse_version(version)
            current = _parse_version(VERSION)
            if parsed == current:
                status = "current"
            elif parsed > current:
                status = "newer"
            else:
                status = "older"
            releases.append(
                {
                    "version": version,
                    "tag": tag,
                    "download_url": appimage_url,
                    "is_current": parsed == current,
                    "status": status,
                }
            )
        return releases
    except Exception:
        return []


def check_for_updates():
    """Return update information when a newer version is available.

    Returns a dict with keys:
        "current"      – the currently installed version string
        "latest"       – the latest release version string from GitHub
        "download_url" – direct download URL for the AppImage asset, or None

    Returns None when Quickr is already up to date or when the check fails.
    """
    result = get_latest_release()
    if result is None:
        return None

    latest, download_url = result
    if not latest:
        return None

    if _parse_version(latest) > _parse_version(VERSION):
        return {
            "current": VERSION,
            "latest": latest,
            "download_url": download_url,
        }
    return None


def do_appimage_update(download_url: str, progress_cb=None) -> bool:
    """Download the new AppImage and replace the currently running binary.

    Parameters
    ----------
    download_url : str
        Direct URL to the new ``.AppImage`` file.
    progress_cb : callable(bytes_done, total_bytes) | None
        Optional callback invoked periodically during the download.  Use this
        to drive a GTK progress bar from the calling thread.

    Returns
    -------
    bool
        True on success, False on any failure.
    """
    appimage_path = os.environ.get("APPIMAGE")
    if not appimage_path:
        return False

    tmp_path = None
    try:
        # Download to a sibling temp file so that the final rename is atomic
        # (source and destination are on the same filesystem).
        dest_dir = os.path.dirname(appimage_path)
        fd, tmp_path = tempfile.mkstemp(suffix=".AppImage", dir=dest_dir)
        os.close(fd)

        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": f"Quickr/{VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            with open(tmp_path, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress_cb is not None:
                        progress_cb(done, total)

        # Make the downloaded file executable
        current_mode = os.stat(tmp_path).st_mode
        os.chmod(
            tmp_path,
            current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )

        # Atomic replace – os.replace handles this on POSIX
        os.replace(tmp_path, appimage_path)
        return True

    except Exception:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False
