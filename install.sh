#!/usr/bin/env bash
# install.sh – Install Quickr on Linux (Arch, Debian/Ubuntu, Fedora and compatible distros)

set -euo pipefail

QUICKR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_BIN="${HOME}/.local/bin"
AUTOSTART_DIR="${HOME}/.config/autostart"

# ── Colour output ──────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[quickr]${NC} $*"; }
warn()  { echo -e "${YELLOW}[quickr]${NC} $*"; }
error() { echo -e "${RED}[quickr]${NC} $*" >&2; }

# ── Detect package manager ─────────────────────────────────────────────────
install_deps() {
    if command -v pacman &>/dev/null; then
        info "Arch / pacman detected – installing deps…"
        sudo pacman -Sy --noconfirm --needed \
            python \
            python-gobject \
            gtk3 \
            gdk-pixbuf2 \
            librsvg \
            xdg-utils
    elif command -v apt-get &>/dev/null; then
        info "Debian / apt detected – installing deps…"
        sudo apt-get install -y \
            python3 \
            python3-gi \
            python3-gi-cairo \
            gir1.2-gtk-3.0 \
            gir1.2-gdkpixbuf-2.0 \
            librsvg2-common \
            xdg-utils
    elif command -v dnf &>/dev/null; then
        info "Fedora / dnf detected – installing deps…"
        sudo dnf install -y \
            python3 \
            python3-gobject \
            gtk3 \
            gdk-pixbuf2 \
            librsvg2 \
            xdg-utils
    else
        warn "Unknown package manager. Please install manually:"
        warn "  - Python 3.9+"
        warn "  - python-gobject (PyGObject)"
        warn "  - GTK 3"
        warn "  - gdk-pixbuf"
        warn "  - xdg-utils"
    fi
}

# ── Self-test ─────────────────────────────────────────────────────────────
check_python() {
    python3 -c "
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gtk, GdkPixbuf
print('GTK3 OK')
" || { error "GTK3 / PyGObject not working – aborting."; exit 1; }
}

# ── Symlink into PATH ─────────────────────────────────────────────────────
link_binary() {
    mkdir -p "${INSTALL_BIN}"
    # Write a small wrapper so the binary works from anywhere
    cat > "${INSTALL_BIN}/quickr" <<EOF
#!/usr/bin/env bash
exec python3 "${QUICKR_DIR}/quickr.py" "\$@"
EOF
    chmod +x "${INSTALL_BIN}/quickr"
    info "Installed: ${INSTALL_BIN}/quickr"

    # Ensure ~/.local/bin is in PATH
    if [[ ":${PATH}:" != *":${INSTALL_BIN}:"* ]]; then
        warn "${INSTALL_BIN} is not in your \$PATH."
        warn "Add this line to your ~/.bashrc or ~/.zshrc:"
        warn "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    fi
}

# ── Autostart (optional) ──────────────────────────────────────────────────
install_autostart() {
    mkdir -p "${AUTOSTART_DIR}"
    cat > "${AUTOSTART_DIR}/quickr.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Quickr
Comment=Quickr minibar
Exec=python3 ${QUICKR_DIR}/quickr.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
    info "Autostart entry created: ${AUTOSTART_DIR}/quickr.desktop"
}

# ── Desktop shortcut ──────────────────────────────────────────────────────
install_desktop_entry() {
    local APPS="${HOME}/.local/share/applications"
    mkdir -p "${APPS}"
    cat > "${APPS}/quickr.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Quickr
Comment=Linux minibar & shortcut launcher
Exec=python3 ${QUICKR_DIR}/quickr.py
Icon=${QUICKR_DIR}/AppDir/quickr.png
Terminal=false
Categories=Utility;
EOF
    update-desktop-database "${APPS}" 2>/dev/null || true
    info "Desktop entry installed."
}

# ── Check for updates ─────────────────────────────────────────────────────
check_for_updates() {
    info "Checking for updates…"
    python3 -c "
import sys, json
sys.path.insert(0, '${QUICKR_DIR}/src')
try:
    from updater import check_for_updates, VERSION, RELEASES_PAGE
    result = check_for_updates()
    if result:
        print('  \u2b06  Update available: v' + result['latest'] + '  (installed: v' + result['current'] + ')')
        print(\"     Run 'quickr update' to update.\")
    else:
        print('  \u2713  Quickr ' + VERSION + ' is up to date.')
except Exception:
    pass
" 2>/dev/null || true
}

# ── Main ──────────────────────────────────────────────────────────────────
main() {
    info "=== Quickr installer ==="
    info "Install directory: ${QUICKR_DIR}"

    install_deps
    check_python
    link_binary
    install_desktop_entry

    read -r -p "$(echo -e "${YELLOW}[quickr]${NC} Install autostart entry (launch on login)? [y/N] ")" reply
    if [[ "${reply,,}" == "y" ]]; then
        install_autostart
    fi

    check_for_updates

    echo
    info "Done! Start Quickr with:  quickr"
    info "Open the editor with:     quickr editor"
    info "Check for updates with:   quickr update"
}

main "$@"
