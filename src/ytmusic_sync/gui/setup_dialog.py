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
)

from ytmusic_sync.auth.ytm_auth import AuthError, YTMAuthManager

_INSTRUCTIONS = """\
<b>Connect your YouTube Music account</b><br><br>
1. Open <b>music.youtube.com</b> in your browser and make sure you're logged in.<br>
2. Open Developer Tools (F12) &rarr; the <b>Console</b> tab.<br>
3. Type <code>copy(document.cookie)</code> and press Enter &mdash; this copies your
   session cookie straight to the clipboard (nothing will print, that's expected).<br>
4. Paste it below and click "Save &amp; Continue".
"""


class SetupDialog(QDialog):
    def __init__(self, auth_manager: YTMAuthManager, parent=None) -> None:
        super().__init__(parent)
        self._auth_manager = auth_manager
        self.setWindowTitle("Connect your YouTube Music account")
        self.resize(520, 320)

        layout = QVBoxLayout(self)

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

        buttons = QDialogButtonBox()
        self._save_button = buttons.addButton("Save && Continue", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        self._save_button.clicked.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        cookie_str = self._paste_box.text().strip()
        if not cookie_str:
            self._status_label.setText("Please paste your cookie first.")
            return
        self._save_button.setEnabled(False)
        self._status_label.setText("Validating...")
        try:
            self._auth_manager.save_from_cookie(cookie_str)
            client = self._auth_manager.load_client()
            self._auth_manager.validate_client(client)
        except AuthError as e:
            self._status_label.setText(str(e))
            self._save_button.setEnabled(True)
            return
        self.accept()
