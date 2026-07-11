from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ytmusic_sync.auth.ytm_auth import AuthError, YTMAuthManager
from ytmusic_sync.config import AppPaths
from ytmusic_sync.gui.cookie_utils import RawCookie, build_cookie_header, has_required_cookie
from ytmusic_sync.gui.setup_dialog import PasteCookieWidget

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://music.youtube.com"
_DEBOUNCE_MS = 800  # wait for a burst of related cookies to settle before validating
_LOAD_TIMEOUT_MS = 20_000  # nudge toward the manual fallback if the page never loads


def _to_raw_cookie(cookie: QNetworkCookie) -> RawCookie:
    return RawCookie(
        name=bytes(cookie.name()).decode("utf-8", errors="replace"),
        value=bytes(cookie.value()).decode("utf-8", errors="replace"),
        domain=cookie.domain(),
    )


class LoginWebViewDialog(QDialog):
    """Logs the user in via an embedded browser and captures the session cookie
    automatically -- no manual copying needed. Falls back to a manual paste page
    if the embedded browser can't load, or the user prefers it.
    """

    def __init__(self, auth_manager: YTMAuthManager, paths: AppPaths, parent=None) -> None:
        super().__init__(parent)
        self._auth_manager = auth_manager
        self._collected: dict[tuple[str, str], RawCookie] = {}
        self._finishing = False

        self.setWindowTitle("Connect your YouTube Music account")
        self.resize(900, 700)

        self._profile = QWebEngineProfile("ytmusic-sync-login", self)
        profile_dir = paths.webview_profile_dir
        self._profile.setPersistentStoragePath(str(profile_dir / "storage"))
        self._profile.setCachePath(str(profile_dir / "cache"))
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self._page = QWebEnginePage(self._profile, self)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)

        self._status_label = QLabel("Log in with your Google account above.")
        self._status_label.setWordWrap(True)

        fallback_button = QPushButton("Trouble logging in? Paste cookie manually")
        fallback_button.setFlat(True)
        fallback_button.clicked.connect(self._show_fallback_page)

        webview_page = QWidget()
        webview_layout = QVBoxLayout(webview_page)
        webview_layout.setContentsMargins(0, 0, 0, 0)
        webview_layout.addWidget(self._view, stretch=1)
        webview_layout.addWidget(self._status_label)
        webview_layout.addWidget(fallback_button)

        self._paste_widget = PasteCookieWidget(auth_manager, self)
        paste_page = QWidget()
        paste_layout = QVBoxLayout(paste_page)
        paste_layout.setContentsMargins(0, 0, 0, 0)
        paste_layout.addWidget(self._paste_widget)
        paste_buttons = QHBoxLayout()
        back_button = QPushButton("Back to automatic login")
        back_button.setFlat(True)
        back_button.clicked.connect(self._show_webview_page)
        paste_save_button = QPushButton("Save && Continue")
        paste_save_button.clicked.connect(self._on_paste_save)
        paste_buttons.addWidget(back_button)
        paste_buttons.addStretch(1)
        paste_buttons.addWidget(paste_save_button)
        paste_layout.addLayout(paste_buttons)
        self._paste_save_button = paste_save_button

        self._stack = QStackedWidget(self)
        self._webview_index = self._stack.addWidget(webview_page)
        self._paste_index = self._stack.addWidget(paste_page)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._finish_login)

        self._load_timeout_timer = QTimer(self)
        self._load_timeout_timer.setSingleShot(True)
        self._load_timeout_timer.setInterval(_LOAD_TIMEOUT_MS)
        self._load_timeout_timer.timeout.connect(self._on_load_timeout)
        self._load_timeout_timer.start()

        cookie_store = self._profile.cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)
        self._page.loadFinished.connect(self._on_load_finished)

        self._view.setUrl(QUrl(_LOGIN_URL))
        # Re-emits any cookies already on disk from a prior session through
        # cookieAdded, so a returning user is picked up without a fresh login.
        cookie_store.loadAllCookies()

    def _on_load_finished(self, ok: bool) -> None:
        self._load_timeout_timer.stop()
        if not ok:
            self._status_label.setText(
                "The embedded browser couldn't load music.youtube.com. "
                "You can try again or use the manual paste option below."
            )

    def _on_load_timeout(self) -> None:
        self._status_label.setText(
            "This is taking a while to load. If it doesn't finish shortly, "
            "use the manual paste option below."
        )

    def _on_cookie_added(self, cookie: QNetworkCookie) -> None:
        raw = _to_raw_cookie(cookie)
        self._collected[(raw.domain, raw.name)] = raw

        if self._finishing:
            return
        if has_required_cookie(self._collected.values()):
            # (Re)start rather than a fixed one-shot: absorbs a burst of cookies
            # that tend to arrive together right after login completes.
            self._debounce_timer.start()

    def _finish_login(self) -> None:
        if self._finishing:
            return
        self._finishing = True
        self._status_label.setText("Validating your session...")
        cookie_str = build_cookie_header(self._collected.values())
        try:
            self._auth_manager.save_from_cookie(cookie_str)
            client = self._auth_manager.load_client()
            self._auth_manager.validate_client(client)
        except AuthError as e:
            # Treat as transient/retryable (e.g. mid-2FA) rather than fatal --
            # keep watching for further cookies rather than clearing state.
            self._finishing = False
            self._status_label.setText(f"Still waiting for login to complete ({e})")
            return
        self.accept()

    def _show_fallback_page(self) -> None:
        self._stack.setCurrentIndex(self._paste_index)

    def _show_webview_page(self) -> None:
        self._stack.setCurrentIndex(self._webview_index)

    def _on_paste_save(self) -> None:
        self._paste_save_button.setEnabled(False)
        if self._paste_widget.try_save():
            self.accept()
        else:
            self._paste_save_button.setEnabled(True)
