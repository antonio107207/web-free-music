from __future__ import annotations

import shutil
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from ytmusic_sync.auth.ytm_auth import YTMAuthManager
from ytmusic_sync.config import AppPaths
from ytmusic_sync.gui.main_window import MainWindow
from ytmusic_sync.logging_conf import configure_logging

_FFMPEG_MISSING_MESSAGE = """\
ffmpeg was not found on your system, but it's required to convert downloaded \
audio to MP3.

Install it with your distro's package manager, for example:
  sudo apt install ffmpeg        (Debian/Ubuntu)
  sudo dnf install ffmpeg        (Fedora)
  sudo pacman -S ffmpeg          (Arch)

Then restart this application.
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("YT Music Sync")

    paths = AppPaths()
    configure_logging(paths.log_dir)

    if shutil.which("ffmpeg") is None:
        QMessageBox.critical(None, "ffmpeg not found", _FFMPEG_MISSING_MESSAGE)
        return 1

    auth_manager = YTMAuthManager(paths)

    window = MainWindow(auth_manager, paths)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
