# PyInstaller spec for the Linux build.
#
# Run from the repo root via packaging/linux/build_deb.sh rather than
# directly -- that script wraps the output into a .deb.
import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent

datas = collect_data_files("ytmusic_sync") + collect_data_files("ytmusicapi")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
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
_QT_MODULE_RE = re.compile(r"libQt6([A-Za-z0-9]+?)\.so")
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

