import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ytmusicapi.auth.types import AuthType

from ytmusic_sync.auth.ytm_auth import AuthError, YTMAuthManager


class FakePaths:
    def __init__(self, tmp_path: Path) -> None:
        self.auth_file = tmp_path / "auth.json"

    def secure_auth_file(self) -> None:
        pass


@pytest.fixture
def auth_manager(tmp_path: Path) -> YTMAuthManager:
    return YTMAuthManager(FakePaths(tmp_path))


def test_save_from_cookie_rejects_empty_input(auth_manager: YTMAuthManager) -> None:
    with pytest.raises(AuthError, match="paste your cookie"):
        auth_manager.save_from_cookie("   ")


def test_load_client_rejects_cookie_missing_required_value(auth_manager: YTMAuthManager) -> None:
    # save_from_cookie itself doesn't validate cookie contents (ytmusicapi's own
    # parser -- invoked at load_client() -- already raises a specific, accurate
    # error for this, so duplicating that check with a fragile substring guess
    # would only risk false rejections; see the __Secure-3PAPISID substring
    # gotcha this replaced: "SAPISID" is NOT a substring of "__Secure-3PAPISID").
    auth_manager.save_from_cookie("LOGIN_INFO=fake; SOME_OTHER_COOKIE=fake")
    with pytest.raises(AuthError, match="__Secure-3PAPISID"):
        auth_manager.load_client()


def test_save_from_cookie_writes_working_browser_auth_file(auth_manager: YTMAuthManager) -> None:
    auth_manager.save_from_cookie("__Secure-3PAPISID=fake_sapisid_value; LOGIN_INFO=fake")

    assert auth_manager.has_saved_auth()
    client = auth_manager.load_client()
    assert client.auth_type == AuthType.BROWSER
    assert client.sapisid == "fake_sapisid_value"


def test_load_client_with_no_saved_auth_raises(auth_manager: YTMAuthManager) -> None:
    with pytest.raises(AuthError, match="No saved credentials"):
        auth_manager.load_client()


def test_load_client_wraps_corrupt_auth_file(auth_manager: YTMAuthManager, tmp_path: Path) -> None:
    auth_manager._paths.auth_file.write_text("not valid json")
    with pytest.raises(AuthError):
        auth_manager.load_client()


def test_validate_client_wraps_json_decode_error(auth_manager: YTMAuthManager) -> None:
    fake_client = MagicMock()
    fake_client.get_library_playlists.side_effect = json.JSONDecodeError("Expecting value", "", 0)

    with pytest.raises(AuthError, match="non-JSON"):
        auth_manager.validate_client(fake_client)


def test_validate_client_passes_through_on_success(auth_manager: YTMAuthManager) -> None:
    fake_client = MagicMock()
    fake_client.get_library_playlists.return_value = []
    auth_manager.validate_client(fake_client)  # should not raise
