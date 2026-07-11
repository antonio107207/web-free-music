from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ytmusic_sync.auth.ytm_auth import AuthError, YTMAuthManager

_INSTRUCTIONS = """\
<b>Connect your YouTube Music account</b><br><br>
1. Open <b>music.youtube.com</b> in your browser and make sure you're logged in.<br>
2. Open Developer Tools (F12) &rarr; the <b>Console</b> tab.<br>
3. Type <code>copy(document.cookie)</code> and press Enter &mdash; this copies your
   session cookie straight to your clipboard (nothing will print, that's expected).<br>
4. Paste it below and click "Save &amp; Continue".
"""


class PasteCookieWidget(QWidget):
    """The manual copy/paste flow: reusable both as the standalone fallback
    SetupDialog and as a fallback page inside LoginWebViewDialog."""

    def __init__(self, auth_manager: YTMAuthManager, parent=None) -> None:
        super().__init__(parent)
        self._auth_manager = auth_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        instructions = QLabel(_INSTRUCTIONS)
        instructions.setWordWrap(True)
        instructions.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(instructions)

        open_button = QPushButton("Open YouTube Music")
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://music.youtube.com"))
        )
        layout.addWidget(open_button)

        self._paste_box = QLineEdit()
        self._paste_box.setPlaceholderText("Paste the copied cookie here...")
        layout.addWidget(self._paste_box)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #c0392b;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    def try_save(self) -> bool:
        """Runs save_from_cookie -> load_client -> validate_client using the
        current text box contents. Returns True on success (caller should
        accept() its dialog); on failure the status label is updated and this
        returns False (caller should keep the dialog open)."""
        cookie_str = self._paste_box.text().strip()
        if not cookie_str:
            self._status_label.setText("Please paste your cookie first.")
            return False
        self._status_label.setText("Validating...")
        try:
            self._auth_manager.save_from_cookie(cookie_str)
            client = self._auth_manager.load_client()
            self._auth_manager.validate_client(client)
        except AuthError as e:
            self._status_label.setText(str(e))
            return False
        return True


class SetupDialog(QDialog):
    """Manual cookie-paste flow as a standalone dialog. Used as the fallback if
    the embedded-browser login (LoginWebViewDialog) can't even be imported."""

    def __init__(self, auth_manager: YTMAuthManager, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect your YouTube Music account")
        self.resize(520, 320)

        self._widget = PasteCookieWidget(auth_manager, self)

        layout = QVBoxLayout(self)
        layout.addWidget(self._widget)

        buttons = QDialogButtonBox()
        self._save_button = buttons.addButton("Save && Continue", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._save_button.clicked.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        self._save_button.setEnabled(False)
        if self._widget.try_save():
            self.accept()
        else:
            self._save_button.setEnabled(True)
