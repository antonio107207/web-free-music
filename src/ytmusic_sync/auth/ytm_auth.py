from __future__ import annotations

import json

import requests
from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError, YTMusicUserError

from ytmusic_sync.config import AppPaths

_ORIGIN = "https://music.youtube.com"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class AuthError(Exception):
    """Raised when saved or freshly-pasted credentials don't work."""


class YTMAuthManager:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    def has_saved_auth(self) -> bool:
        return self._paths.auth_file.exists()

    def save_from_cookie(self, cookie_str: str) -> None:
        """Builds and saves a browser-auth credentials file from just a `cookie`
        header value (e.g. the output of `document.cookie` on music.youtube.com).

        ytmusicapi only needs the raw cookie: it derives the SAPISID value from the
        cookie itself and recomputes a fresh `authorization: SAPISIDHASH ...` header
        on every request -- the "authorization" entry below is a placeholder that's
        never actually sent; it only needs to *look* like a SAPISIDHASH value so
        ytmusicapi classifies these credentials as browser-auth. See ytmusicapi's
        YTMusicBase.headers property and helpers.sapisid_from_cookie/get_authorization.
        """
        cookie_str = cookie_str.strip()
        if not cookie_str:
            raise AuthError("Please paste your cookie value first.")

        headers = {
            "cookie": cookie_str,
            "x-goog-authuser": "0",
            "origin": _ORIGIN,
            "authorization": "SAPISIDHASH 0_0",
            "user-agent": _USER_AGENT,
            "content-type": "application/json",
            "accept": "*/*",
        }
        self._paths.auth_file.write_text(json.dumps(headers, indent=2))
        self._paths.secure_auth_file()

    def load_client(self) -> YTMusic:
        if not self.has_saved_auth():
            raise AuthError("No saved credentials found.")
        try:
            return YTMusic(auth=str(self._paths.auth_file))
        except (YTMusicUserError, YTMusicServerError, json.JSONDecodeError) as e:
            raise AuthError(
                f"Could not load your saved credentials: {e}. Try reconnecting your "
                "account with a fresh cookie."
            ) from e

    def validate_client(self, client: YTMusic) -> None:
        try:
            client.get_library_playlists(limit=1)
        except (YTMusicServerError, YTMusicUserError) as e:
            raise AuthError(f"Credentials are invalid or expired: {e}") from e
        except json.JSONDecodeError as e:
            raise AuthError(
                "YouTube Music returned an unexpected (non-JSON) response instead of your "
                "library data. This usually means the cookie is stale or you were logged "
                "out in the browser tab you copied it from. Please open music.youtube.com "
                "again, make sure you're logged in, and paste a fresh cookie."
            ) from e
        except requests.RequestException as e:
            raise AuthError(f"Could not reach YouTube Music: {e}") from e
