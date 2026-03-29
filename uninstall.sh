#!/usr/bin/env bash
# uninstall.sh – Remove files placed by install.sh
#
# This script only removes:
#   ~/.local/bin/quickr
#   ~/.config/autostart/quickr.desktop
#   ~/.local/share/applications/quickr.desktop
#   ~/.config/quickr/  (optional, with confirmation)
#
# It does NOT touch the source directory you cloned Quickr into.

set -euo pipefail

INSTALL_BIN="${HOME}/.local/bin"
AUTOSTART_DIR="${HOME}/.config/autostart"
APPS="${HOME}/.local/share/applications"

# ── Colour output ──────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[quickr]${NC} $*"; }
warn()  { echo -e "${YELLOW}[quickr]${NC} $*"; }

info "=== Quickr uninstaller ==="

removed_any=false

# ── Binary wrapper ─────────────────────────────────────────────────────────
if [[ -f "${INSTALL_BIN}/quickr" ]]; then
    rm -f "${INSTALL_BIN}/quickr"
    info "Removed: ${INSTALL_BIN}/quickr"
    removed_any=true
fi

# ── Autostart entry ────────────────────────────────────────────────────────
if [[ -f "${AUTOSTART_DIR}/quickr.desktop" ]]; then
    rm -f "${AUTOSTART_DIR}/quickr.desktop"
    info "Removed: ${AUTOSTART_DIR}/quickr.desktop"
    removed_any=true
fi

# ── Desktop entry ──────────────────────────────────────────────────────────
if [[ -f "${APPS}/quickr.desktop" ]]; then
    rm -f "${APPS}/quickr.desktop"
    update-desktop-database "${APPS}" 2>/dev/null || true
    info "Removed: ${APPS}/quickr.desktop"
    removed_any=true
fi

if [[ "${removed_any}" == "false" ]]; then
    warn "Nothing to remove – no installed Quickr files found."
fi

# ── Config files (optional) ────────────────────────────────────────────────
CONFIG_DIR="${HOME}/.config/quickr"
if [[ -d "${CONFIG_DIR}" ]]; then
    read -r -p "$(echo -e "${YELLOW}[quickr]${NC} Remove configuration directory (${CONFIG_DIR})? [y/N] ")" reply
    if [[ "${reply,,}" == "y" ]]; then
        rm -rf "${CONFIG_DIR}"
        info "Removed: ${CONFIG_DIR}"
    fi
fi

echo
info "Quickr has been uninstalled."
info "The source directory (this folder) was NOT removed."
