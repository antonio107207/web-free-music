from pathlib import Path

import pytest
from PySide6.QtNetwork import QNetworkCookie

from ytmusic_sync.gui.login_web_view_dialog import LoginWebViewDialog


class FakePaths:
    def __init__(self, tmp_path: Path) -> None:
        self.webview_profile_dir = tmp_path / "webview_profile"


class FakeAuthManager:
    def __init__(self, fail_times: int = 0) -> None:
        self.saved_cookie = None
        self._fail_times = fail_times
        self._attempts = 0

    def save_from_cookie(self, cookie_str: str) -> None:
        self.saved_cookie = cookie_str

    def load_client(self):
        return object()

    def validate_client(self, client) -> None:
        self._attempts += 1
        if self._attempts <= self._fail_times:
            from ytmusic_sync.auth.ytm_auth import AuthError

            raise AuthError("not ready yet")


def _make_cookie(name: str, value: str, domain: str) -> QNetworkCookie:
    cookie = QNetworkCookie(name.encode(), value.encode())
    cookie.setDomain(domain)
    return cookie


def test_dialog_does_not_finish_before_required_cookie_arrives(qtbot, tmp_path: Path) -> None:
    auth_manager = FakeAuthManager()
    dialog = LoginWebViewDialog(auth_manager, FakePaths(tmp_path))
    qtbot.addWidget(dialog)

    dialog._on_cookie_added(_make_cookie("SIDCC", "abc", ".youtube.com"))
    qtbot.wait(200)

    assert auth_manager.saved_cookie is None
    assert dialog.result() == 0  # not accepted/rejected yet


def test_dialog_auto_finishes_after_required_cookie_and_debounce(qtbot, tmp_path: Path) -> None:
    auth_manager = FakeAuthManager()
    dialog = LoginWebViewDialog(auth_manager, FakePaths(tmp_path))
    qtbot.addWidget(dialog)

    dialog._on_cookie_added(_make_cookie("SIDCC", "abc", ".youtube.com"))
    dialog._on_cookie_added(_make_cookie("__Secure-3PAPISID", "sapisid-value", ".youtube.com"))

    qtbot.waitUntil(lambda: auth_manager.saved_cookie is not None, timeout=3000)
    assert "__Secure-3PAPISID=sapisid-value" in auth_manager.saved_cookie
    assert "SIDCC=abc" in auth_manager.saved_cookie
    qtbot.waitUntil(lambda: dialog.result() == LoginWebViewDialog.DialogCode.Accepted, timeout=3000)


def test_off_domain_cookies_are_excluded_from_saved_header(qtbot, tmp_path: Path) -> None:
    auth_manager = FakeAuthManager()
    dialog = LoginWebViewDialog(auth_manager, FakePaths(tmp_path))
    qtbot.addWidget(dialog)

    dialog._on_cookie_added(_make_cookie("session", "google-session", "accounts.google.com"))
    dialog._on_cookie_added(_make_cookie("__Secure-3PAPISID", "sapisid-value", ".youtube.com"))

    qtbot.waitUntil(lambda: auth_manager.saved_cookie is not None, timeout=3000)
    assert "session=google-session" not in auth_manager.saved_cookie


def test_transient_validation_failure_keeps_dialog_open_and_retries(qtbot, tmp_path: Path) -> None:
    # Simulates the required cookie appearing before login is *fully* complete
    # (e.g. mid-2FA): the first validate_client() call fails, the dialog must
    # stay open and NOT discard already-collected cookies, so a later retry
    # (triggered by another cookie arriving) can succeed.
    auth_manager = FakeAuthManager(fail_times=1)
    dialog = LoginWebViewDialog(auth_manager, FakePaths(tmp_path))
    qtbot.addWidget(dialog)

    dialog._on_cookie_added(_make_cookie("__Secure-3PAPISID", "sapisid-value", ".youtube.com"))
    qtbot.waitUntil(lambda: dialog._finishing is False and auth_manager._attempts == 1, timeout=3000)
    assert dialog.result() == 0  # still open after the soft failure

    # a further cookie arrival re-triggers the debounce -> retry -> succeeds
    dialog._on_cookie_added(_make_cookie("extra", "value", ".youtube.com"))
    qtbot.waitUntil(lambda: auth_manager.saved_cookie is not None, timeout=3000)
    qtbot.waitUntil(lambda: dialog.result() == LoginWebViewDialog.DialogCode.Accepted, timeout=3000)


def test_fallback_button_switches_to_paste_page(qtbot, tmp_path: Path) -> None:
    dialog = LoginWebViewDialog(FakeAuthManager(), FakePaths(tmp_path))
    qtbot.addWidget(dialog)

    assert dialog._stack.currentIndex() == dialog._webview_index
    dialog._show_fallback_page()
    assert dialog._stack.currentIndex() == dialog._paste_index

    dialog._show_webview_page()
    assert dialog._stack.currentIndex() == dialog._webview_index
