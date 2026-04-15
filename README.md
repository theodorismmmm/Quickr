# Quickr

A minimal, sleek Linux minibar (dock) that lets you pin shortcuts to apps, files, folders, and URLs — all accessible from a slim panel at the bottom of your screen.

---

## Features

| Feature | Detail |
|---|---|
| **Minibar / Dock** | Slim, always-on-top dark panel at the bottom of the screen |
| **Shortcut types** | Apps (`.desktop` or binary), Files, Folders, URLs |
| **Smart icons** | Reads app icons from `.desktop` files; shows mime-type icons for files/folders; uses a globe icon for URLs with a domain label |
| **Editor** | Full GTK3 editor — only opened via the terminal (`quickr editor`) |
| **Arch-first** | Built with system GTK3, no Electron, minimal footprint |
| **AppImage** | One-file portable build via `build-appimage.sh` |

---

## Quick start

### 1 · Install dependencies

**Arch / Manjaro**
```bash
sudo pacman -S python-gobject gtk3 gdk-pixbuf2 librsvg xdg-utils
```

**Debian / Ubuntu**
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
                 gir1.2-gdkpixbuf-2.0 librsvg2-common xdg-utils
```

**Fedora**
```bash
sudo dnf install python3-gobject gtk3 gdk-pixbuf2 librsvg2 xdg-utils
```

**SteamOS (Steam Deck)**

The root filesystem is read-only on SteamOS, so `install.sh` skips automatic
package installation and continues with the rest of the setup.  
If the required packages are missing, unlock the rootfs first:

```bash
sudo steamos-readonly disable
sudo pacman -Sy --noconfirm --needed python python-gobject gtk3 gdk-pixbuf2 librsvg xdg-utils
sudo steamos-readonly enable
```

### 2 · Install Quickr

```bash
git clone https://github.com/theodorismmmm/Quickr.git
cd Quickr
bash install.sh
```

The installer:
- Installs system dependencies for your distro (skipped on SteamOS — see above)
- Creates `~/.local/bin/quickr` on your `$PATH`
- Adds an optional autostart entry so the bar launches on login

### 3 · Run

```bash
# Start the minibar
quickr

# Open the shortcut editor
quickr editor
```

---

## Uninstalling

```bash
# Via the CLI
quickr uninstall

# Or directly with the uninstall script
bash uninstall.sh
```

Both commands remove only the files that `install.sh` placed on the system
(`~/.local/bin/quickr`, desktop entries) and optionally the configuration
directory (`~/.config/quickr/`).  
The source directory you cloned is **never** touched.

---

## Editing shortcuts

The bar is **read-only at runtime** — you can only add/remove/edit shortcuts through the editor:

```bash
quickr editor
```

This opens a GTK window where you can:

- **Add** shortcuts (type, name, path/URL)
- **Edit** existing shortcuts
- **Delete** shortcuts
- **Browse** for files, folders, or app binaries

Changes are saved to `~/.config/quickr/shortcuts.json` and are picked up the next time the bar starts.

### Supported types

| Type | Example path |
|---|---|
| `app` | `/usr/bin/firefox` or `/usr/share/applications/firefox.desktop` |
| `file` | `/home/you/Documents/notes.txt` |
| `folder` | `/home/you/Projects` |
| `url` | `https://github.com` |

---

## Build an AppImage

```bash
# Download appimagetool first
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage

# Build
bash build-appimage.sh
./Quickr.AppImage           # run the bar
./Quickr.AppImage editor    # run the editor
```

> **Note:** GTK3 and PyGObject must be installed on the host system.  
> The AppImage bundles the Python source only (no full runtime).

---

## Build a Windows executable (GitHub Action)

A GitHub Actions workflow is available at:

`.github/workflows/build-windows-exe.yml`

It builds a Windows `.exe` with PyInstaller:

- On tag pushes matching `v*` (also uploads to the GitHub release)
- On manual runs via **workflow_dispatch** (uploads as workflow artifact)

---

## Project layout

```
Quickr/
├── src/
│   ├── bar.py         # Minibar GTK3 window
│   ├── editor.py      # Editor GTK3 window
│   ├── config.py      # JSON config management
│   └── icons.py       # Icon resolution helpers
├── quickr.py          # Entry point (bar, editor, update, uninstall)
├── quickr             # Shell wrapper (symlinked to ~/.local/bin/quickr)
├── install.sh         # Installer
├── uninstall.sh       # Uninstaller (removes installed files only)
├── build-appimage.sh  # AppImage builder
├── AppDir/            # AppImage directory skeleton
└── requirements.txt
```

---

## Configuration file

`~/.config/quickr/shortcuts.json`

```json
{
  "shortcuts": [
    {
      "id": "…",
      "type": "app",
      "name": "Firefox",
      "path": "/usr/share/applications/firefox.desktop"
    },
    {
      "id": "…",
      "type": "url",
      "name": "GitHub",
      "path": "https://github.com"
    }
  ]
}
```

---

## License

MIT
