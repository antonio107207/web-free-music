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

APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"

# Using the icon's absolute path directly (rather than installing it into the
# XDG icon theme and referencing it by name) sidesteps icon-theme-cache
# lookup flakiness -- the theme-name approach didn't reliably render on all
# desktops we tested. The path below is filled in fresh on whatever machine
# this script runs on, so the *installed* .desktop file is machine-specific --
# only the git-tracked ytmusic-sync.desktop.in template stays portable.
DESKTOP_FILE="$APPS_DIR/ytmusic-sync.desktop"
sed -e "s|@EXEC@|$VENV_BIN|" -e "s|@ICON@|$ICON_SOURCE|" "$TEMPLATE" > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"
echo "Installed app-menu entry: $DESKTOP_FILE"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/Desktop}"
if [[ -d "$DESKTOP_DIR" ]]; then
    cp "$DESKTOP_FILE" "$DESKTOP_DIR/ytmusic-sync.desktop"
    chmod +x "$DESKTOP_DIR/ytmusic-sync.desktop"
    echo "Installed Desktop icon: $DESKTOP_DIR/ytmusic-sync.desktop"
    # GNOME/Nautilus deliberately shows untrusted .desktop files with a generic
    # icon and won't run them until you confirm this once via its own UI -- there
    # is no supported CLI/gio way to pre-approve this (by design, to stop scripts
    # from silently self-trusting an executable).
    echo "Right-click it in Nautilus and choose 'Allow Launching' to see the real icon and enable double-click launch."
fi

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" || true

echo "Done."
