from ytmusic_sync.gui.cookie_utils import (
    REQUIRED_COOKIE_NAME,
    RawCookie,
    build_cookie_header,
    has_required_cookie,
    is_relevant_cookie,
)


def test_is_relevant_cookie_matches_youtube_domain_variants() -> None:
    assert is_relevant_cookie(RawCookie("a", "1", "music.youtube.com"))
    assert is_relevant_cookie(RawCookie("a", "1", ".youtube.com"))
    assert not is_relevant_cookie(RawCookie("a", "1", "accounts.google.com"))
    assert not is_relevant_cookie(RawCookie("a", "1", "notyoutube.com"))


def test_has_required_cookie_true_only_when_present_and_relevant() -> None:
    assert not has_required_cookie([])
    assert not has_required_cookie([RawCookie("other", "1", "music.youtube.com")])
    assert not has_required_cookie([RawCookie(REQUIRED_COOKIE_NAME, "1", "accounts.google.com")])
    assert has_required_cookie([RawCookie(REQUIRED_COOKIE_NAME, "1", "music.youtube.com")])


def test_build_cookie_header_joins_in_document_cookie_format() -> None:
    cookies = [
        RawCookie("a", "1", "music.youtube.com"),
        RawCookie("b", "2", ".youtube.com"),
    ]
    assert build_cookie_header(cookies) == "a=1; b=2"


def test_build_cookie_header_excludes_off_domain_cookies() -> None:
    cookies = [
        RawCookie("a", "1", "music.youtube.com"),
        RawCookie("session", "xyz", "accounts.google.com"),
    ]
    assert build_cookie_header(cookies) == "a=1"


def test_build_cookie_header_dedupes_by_name_last_write_wins() -> None:
    cookies = [
        RawCookie("a", "old", "music.youtube.com"),
        RawCookie("a", "new", "music.youtube.com"),
    ]
    assert build_cookie_header(cookies) == "a=new"


def test_build_cookie_header_empty_input() -> None:
    assert build_cookie_header([]) == ""
