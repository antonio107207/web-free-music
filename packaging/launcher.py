"""PyInstaller entry point. PyInstaller needs a script file rather than the
`ytmusic_sync.app:main` console-script reference from pyproject.toml.

With YTS_SMOKE_TEST=1 the frozen app instead checks that the pieces most
likely to break in a bundle actually work -- QtWebEngine can render a page
and ffmpeg is discoverable -- then exits 0 on success. CI runs this on every
build.
"""
import os
import sys


def _smoke_test() -> int:
    import shutil

    from PySide6.QtCore import QTimer
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        print(f"smoke: {tool} = {found}", flush=True)
        if found is None:
            return 1

    result = {"ok": False}
    view = QWebEngineView()

    def on_load_finished(ok: bool) -> None:
        result["ok"] = ok
        app.quit()

    view.loadFinished.connect(on_load_finished)
    view.setHtml("<html><body>smoke</body></html>")
    QTimer.singleShot(60_000, app.quit)
    app.exec()
    print(f"smoke: webengine load ok = {result['ok']}", flush=True)
    return 0 if result["ok"] else 1


if os.environ.get("YTS_SMOKE_TEST") == "1":
    sys.exit(_smoke_test())

from ytmusic_sync.app import main

sys.exit(main())
