from ytmusic_sync.auth.ytm_auth import AuthError
from ytmusic_sync.gui.setup_dialog import SetupDialog


class FakeAuthManager:
    def __init__(self, fail: bool = False) -> None:
        self.saved_cookie = None
        self._fail = fail

    def save_from_cookie(self, cookie_str: str) -> None:
        self.saved_cookie = cookie_str

    def load_client(self):
        return object()

    def validate_client(self, client) -> None:
        if self._fail:
            raise AuthError("nope")


def test_empty_paste_shows_error_and_does_not_accept(qtbot) -> None:
    dialog = SetupDialog(FakeAuthManager())
    qtbot.addWidget(dialog)

    dialog._on_save()

    assert dialog.result() == 0
    assert "paste your cookie" in dialog._widget._status_label.text()


def test_successful_paste_accepts_dialog(qtbot) -> None:
    auth_manager = FakeAuthManager()
    dialog = SetupDialog(auth_manager)
    qtbot.addWidget(dialog)

    dialog._widget._paste_box.setText("__Secure-3PAPISID=abc; LOGIN_INFO=fake")
    dialog._on_save()

    assert auth_manager.saved_cookie == "__Secure-3PAPISID=abc; LOGIN_INFO=fake"
    assert dialog.result() == SetupDialog.DialogCode.Accepted


def test_failed_validation_keeps_dialog_open(qtbot) -> None:
    dialog = SetupDialog(FakeAuthManager(fail=True))
    qtbot.addWidget(dialog)

    dialog._widget._paste_box.setText("__Secure-3PAPISID=abc")
    dialog._on_save()

    assert dialog.result() == 0
    assert dialog._save_button.isEnabled()
