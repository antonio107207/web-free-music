#!/usr/bin/env bash
# Builds dist/ytmusic-sync_<version>_macos-<arch>.dmg from the current checkout.
#
# Run on macOS with the project venv active and PyInstaller installed:
#   pip install -e ".[build]"
# The .dmg targets the architecture of the Python running the build (arm64 on
# Apple Silicon, x86_64 on Intel). Static ffmpeg/ffprobe builds are downloaded
# and bundled inside the .app, since macOS doesn't ship ffmpeg.
#
# The app is only ad-hoc signed, so on first launch Gatekeeper will refuse it:
# right-click the app > Open (or System Settings > Privacy & Security > Open
# Anyway) once. Proper signing + notarization needs an Apple Developer ID.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VERSION="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
ARCH="$(python -c 'import platform; print(platform.machine())')"
APP_NAME="YT Music Sync"
WORK="build/macos"
OUT="dist/ytmusic-sync_${VERSION}_macos-${ARCH}.dmg"

case "$ARCH" in
    arm64) FFMPEG_ARCH=arm64 ;;
    x86_64) FFMPEG_ARCH=amd64 ;;
    *) echo "error: unsupported architecture $ARCH" >&2; exit 1 ;;
esac

rm -rf "$WORK"
mkdir -p "$WORK/ffmpeg" dist

# --- ffmpeg + ffprobe (static builds by Martin Riedl, https://ffmpeg.martin-riedl.de)
FFMPEG_BASE_URL="${FFMPEG_BASE_URL:-https://ffmpeg.martin-riedl.de/redirect/latest/macos/$FFMPEG_ARCH/release}"
for tool in ffmpeg ffprobe; do
    curl -fL --retry 3 -o "$WORK/$tool.zip" "$FFMPEG_BASE_URL/$tool.zip"
    unzip -o -q "$WORK/$tool.zip" -d "$WORK/ffmpeg"
    chmod +x "$WORK/ffmpeg/$tool"
    # Fail early if the download is for the wrong CPU or not a binary at all.
    file "$WORK/ffmpeg/$tool" | grep -q "$ARCH" || { file "$WORK/ffmpeg/$tool"; exit 1; }
done

# --- .icns from the 512px PNG
ICONSET="$WORK/icon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z $size $size yts-icon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    if [ $double -le 512 ]; then
        sips -z $double $double yts-icon.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
    fi
done
iconutil -c icns "$ICONSET" -o "$WORK/icon.icns"

# --- .app
YTS_VERSION="$VERSION" YTS_FFMPEG_DIR="$ROOT/$WORK/ffmpeg" YTS_ICNS="$ROOT/$WORK/icon.icns" \
    pyinstaller --noconfirm --clean \
    --distpath "$WORK/dist" --workpath "$WORK/pyinstaller" \
    packaging/ytmusic-sync.spec

APP="$WORK/dist/$APP_NAME.app"
# Re-sign the whole bundle ad-hoc so the bundled ffmpeg binaries are covered
# too; unsigned code doesn't run at all on Apple Silicon.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

# --- .dmg with the usual drag-to-Applications layout
DMG_ROOT="$WORK/dmg"
mkdir -p "$DMG_ROOT"
cp -R "$APP" "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"
rm -f "$OUT"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_ROOT" -fs HFS+ -format UDZO "$OUT"
echo "Built $OUT"
