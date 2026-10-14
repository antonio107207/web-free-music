from __future__ import annotations

import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from ytmusic_sync.auth.ytm_auth import YTMAuthManager
from ytmusic_sync.config import AppPaths
from ytmusic_sync.gui.main_window import MainWindow
from ytmusic_sync.logging_conf import configure_logging

_FFMPEG_MISSING_MESSAGE = """\
ffmpeg was not found on your system, but it's required to convert downloaded \
audio to MP3.

Install it with your package manager, for example:
  sudo apt install ffmpeg        (Debian/Ubuntu)
  sudo dnf install ffmpeg        (Fedora)
  sudo pacman -S ffmpeg          (Arch)
  brew install ffmpeg            (macOS)

Then restart this application.
"""

# GUI apps launched from Finder get a minimal PATH that doesn't include
# Homebrew, so a brew-installed ffmpeg would otherwise go unnoticed.
_MACOS_EXTRA_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def _extend_path_for_ffmpeg() -> None:
    """Makes ffmpeg/ffprobe discoverable by both our startup check and yt-dlp,
    which looks them up on PATH. Packaged builds may ship their own copies in
    a bin/ directory next to the bundled Python code (the macOS .app does).
    """
    extra_dirs: list[str] = []
    if getattr(sys, "frozen", False):
        bundled_bin = Path(getattr(sys, "_MEIPASS", "")) / "bin"
        if bundled_bin.is_dir():
            extra_dirs.append(str(bundled_bin))
    if sys.platform == "darwin":
        extra_dirs.extend(d for d in _MACOS_EXTRA_BIN_DIRS if os.path.isdir(d))
    if extra_dirs:
        os.environ["PATH"] = os.pathsep.join([*extra_dirs, os.environ.get("PATH", "")])


def _load_app_icon() -> QIcon:
    icon_path = resources.files("ytmusic_sync.resources").joinpath("icon.png")
    return QIcon(str(icon_path))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("YT Music Sync")
    app.setWindowIcon(_load_app_icon())

    paths = AppPaths()
    configure_logging(paths.log_dir)

    _extend_path_for_ffmpeg()
    if shutil.which("ffmpeg") is None:
        QMessageBox.critical(None, "ffmpeg not found", _FFMPEG_MISSING_MESSAGE)
        return 1

    auth_manager = YTMAuthManager(paths)

    window = MainWindow(auth_manager, paths)
    window.setWindowIcon(app.windowIcon())
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
