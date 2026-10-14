#!/usr/bin/env bash
# Builds dist/ytmusic-sync_<version>_<arch>.deb from the current checkout.
#
# Run on the oldest Ubuntu you want to support (the bundled binaries link
# against the build machine's glibc), with the project venv active and
# PyInstaller installed:  pip install -e ".[build]"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VERSION="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
ARCH="$(dpkg --print-architecture)"
PKG="ytmusic-sync"
STAGE="build/deb/${PKG}_${VERSION}_${ARCH}"
OUT="dist/${PKG}_${VERSION}_${ARCH}.deb"

pyinstaller --noconfirm --clean \
    --distpath build/pyinstaller/dist --workpath build/pyinstaller/work \
    packaging/ytmusic-sync.spec

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt" "$STAGE/usr/bin" \
    "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/512x512/apps"

cp -a build/pyinstaller/dist/ytmusic-sync "$STAGE/opt/$PKG"
ln -s "/opt/$PKG/ytmusic-sync" "$STAGE/usr/bin/ytmusic-sync"
install -m 644 yts-icon.png "$STAGE/usr/share/icons/hicolor/512x512/apps/$PKG.png"
sed -e "s|@EXEC@|ytmusic-sync|" -e "s|@ICON@|$PKG|" ytmusic-sync.desktop.in \
    > "$STAGE/usr/share/applications/$PKG.desktop"
chmod 644 "$STAGE/usr/share/applications/$PKG.desktop"

# Don't let the builder's umask leak group-writable dirs into the package.
chmod -R u+rwX,go+rX,go-w "$STAGE"

INSTALLED_SIZE_KB="$(du -sk "$STAGE" | cut -f1)"

# Qt itself is bundled, but the xcb platform plugin and QtWebEngine still load
# a few system libraries that a minimal Ubuntu install may not have.
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: Anton Dombrovskii <noreply@users.noreply.github.com>
Installed-Size: $INSTALLED_SIZE_KB
Depends: ffmpeg, libxcb-cursor0, libxkbcommon-x11-0, libegl1, libnss3, libfontconfig1
Section: sound
Priority: optional
Homepage: https://github.com/antonio107207/web-free-music
Description: Sync your YouTube Music playlists to a local MP3 library
 Desktop app that backs up your own YouTube Music playlists and liked songs
 as tagged MP3 files.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
EOF
cp "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

mkdir -p dist
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"
echo "Built $OUT"
