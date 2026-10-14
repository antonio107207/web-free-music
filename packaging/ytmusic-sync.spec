# PyInstaller spec shared by the Linux and macOS builds.
#
# Run from the repo root via packaging/linux/build_deb.sh or
# packaging/macos/build_dmg.sh rather than directly -- those scripts set the
# environment variables read below and wrap the output into an installer.
#
#   YTS_VERSION     app version for the macOS Info.plist (default 0.0.0)
#   YTS_FFMPEG_DIR  directory holding ffmpeg + ffprobe binaries to bundle
#                   into bin/ (macOS only; Linux depends on the distro's ffmpeg)
#   YTS_ICNS        path to the .icns icon for the macOS .app
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
APP_NAME = "YT Music Sync"
VERSION = os.environ.get("YTS_VERSION", "0.0.0")

datas = collect_data_files("ytmusic_sync") + collect_data_files("ytmusicapi")

binaries = []
ffmpeg_dir = os.environ.get("YTS_FFMPEG_DIR")
if ffmpeg_dir:
    for tool in ("ffmpeg", "ffprobe"):
        binaries.append((str(Path(ffmpeg_dir) / tool), "bin"))

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    # Test-only Qt modules that PySide6's hooks would otherwise drag in.
    excludes=["pytest", "pytestqt", "PySide6.QtTest"],
)

# PySide6's hooks pull in the whole qml/ tree, which drags along ~100 Qt
# modules (3D, Charts, Multimedia, ...) the app never loads. Keep only what
# Widgets + WebEngine (and the platform plugins) actually link against.
# That's ~350 MB less on Linux.
QT_MODULES_KEEP = {
    "Core", "Gui", "Widgets", "Network", "DBus", "Svg", "OpenGL", "OpenGLWidgets",
    "PrintSupport", "Positioning", "WebChannel", "WebEngineCore", "WebEngineWidgets",
    "Qml", "QmlMeta", "QmlModels", "QmlWorkerScript", "Quick", "QuickWidgets",
    "XcbQpa", "WaylandClient", "WlShellIntegration", "EglFSDeviceIntegration",
    "EglFsKmsSupport",
}
# libQt6Foo.so.6 on Linux, QtFoo.framework/... on macOS.
_QT_MODULE_RE = re.compile(r"(?:libQt6|(?:^|/)Qt)([A-Za-z0-9]+?)(?:\.so|\.framework)")
_DROP_PREFIXES = tuple(
    os.path.join("PySide6", "Qt", *parts)
    for parts in (("qml",), ("plugins", "qmltooling"), ("plugins", "position"))
)


def _keep(dest: str) -> bool:
    if dest.startswith(_DROP_PREFIXES):
        return False
    name = os.path.basename(dest)
    # Qt's own UI translations (the app is English-only) and WebEngine locale
    # packs other than the en-US fallback Chromium always loads.
    if re.fullmatch(r"qt\w*_[a-zA-Z_]+\.qm", name):
        return False
    if "qtwebengine_locales" in dest and name != "en-US.pak":
        return False
    match = _QT_MODULE_RE.search(dest)
    return match is None or match.group(1) in QT_MODULES_KEEP


a.binaries = [entry for entry in a.binaries if _keep(entry[0])]
a.datas = [entry for entry in a.datas if _keep(entry[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ytmusic-sync",
    console=False,
    strip=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ytmusic-sync",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=os.environ.get("YTS_ICNS"),
        bundle_identifier="io.github.antonio107207.ytmusic-sync",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
