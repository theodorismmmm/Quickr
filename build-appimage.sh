#!/usr/bin/env bash
# build-appimage.sh – Build a self-contained AppImage for Quickr
#
# Requirements:
#   - appimagetool  (download from https://github.com/AppImage/AppImageKit/releases)
#   - Python 3 + PyGObject + GTK3 are available system-wide (bundled is complex)
#
# The resulting AppImage is a thin launcher that runs the Python source
# from inside the AppDir.  GTK3 / PyGObject must be installed on the host.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPDIR="${SCRIPT_DIR}/AppDir"
OUT="${SCRIPT_DIR}/Quickr.AppImage"

# ── Locate appimagetool ────────────────────────────────────────────────────
if command -v appimagetool &>/dev/null; then
    APPIMAGETOOL="appimagetool"
elif [[ -f "${SCRIPT_DIR}/appimagetool-x86_64.AppImage" ]]; then
    APPIMAGETOOL="${SCRIPT_DIR}/appimagetool-x86_64.AppImage"
else
    echo "[build] appimagetool not found."
    echo "Download from: https://github.com/AppImage/AppImageKit/releases/latest"
    echo "  wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    echo "  chmod +x appimagetool-x86_64.AppImage"
    exit 1
fi

# ── Copy source into AppDir ────────────────────────────────────────────────
echo "[build] Preparing AppDir…"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/quickr"

cp -r "${SCRIPT_DIR}/src/"* "${APPDIR}/usr/share/quickr/"
cp    "${SCRIPT_DIR}/quickr.py"  "${APPDIR}/usr/share/quickr/"

# ── Build ──────────────────────────────────────────────────────────────────
echo "[build] Running appimagetool…"
ARCH=x86_64 "${APPIMAGETOOL}" "${APPDIR}" "${OUT}"

echo
echo "[build] Done → ${OUT}"
echo "Run with:  ./Quickr.AppImage"
echo "Run editor: ./Quickr.AppImage editor"
