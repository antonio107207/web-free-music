#!/usr/bin/env bash
# Installs a desktop launcher (app menu + optional Desktop icon) for the
# current checkout, using this machine's actual paths -- nothing here is
# hardcoded, so it's safe to run after cloning the repo anywhere.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="$PROJECT_ROOT/.venv/bin/ytmusic-sync"
ICON_SOURCE="$PROJECT_ROOT/yts-icon.png"
TEMPLATE="$PROJECT_ROOT/ytmusic-sync.desktop.in"

if [[ ! -x "$VENV_BIN" ]]; then
    echo "error: $VENV_BIN not found." >&2
    echo "Create the venv and install the app first, e.g.:" >&2
    echo "  python3 -m venv \"$PROJECT_ROOT/.venv\" && \"$PROJECT_ROOT/.venv/bin/pip\" install -e \"$PROJECT_ROOT[dev]\"" >&2
    exit 1
fi

ICON_NAME="ytmusic-sync"
ICON_THEME_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_THEME_DIR" "$APPS_DIR"

# Installing the icon into the standard XDG icon theme location lets the
# desktop file reference it by name (Icon=ytmusic-sync) instead of an
# absolute path, so the .desktop file itself stays portable/re-runnable.
cp "$ICON_SOURCE" "$ICON_THEME_DIR/$ICON_NAME.png"

DESKTOP_FILE="$APPS_DIR/ytmusic-sync.desktop"
sed -e "s|@EXEC@|$VENV_BIN|" -e "s|@ICON@|$ICON_NAME|" "$TEMPLATE" > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"
echo "Installed app-menu entry: $DESKTOP_FILE"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/Desktop}"
if [[ -d "$DESKTOP_DIR" ]]; then
    cp "$DESKTOP_FILE" "$DESKTOP_DIR/ytmusic-sync.desktop"
    chmod +x "$DESKTOP_DIR/ytmusic-sync.desktop"
    gio set "$DESKTOP_DIR/ytmusic-sync.desktop" metadata::trusted true 2>/dev/null || true
    echo "Installed Desktop icon: $DESKTOP_DIR/ytmusic-sync.desktop"
    echo "If your file manager still shows it as untrusted, right-click it and choose 'Allow Launching'."
fi

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Done."
