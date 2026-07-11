from __future__ import annotations

from dataclasses import dataclass

REQUIRED_COOKIE_NAME = "__Secure-3PAPISID"
_RELEVANT_DOMAIN_SUFFIX = "youtube.com"


@dataclass(frozen=True)
class RawCookie:
    name: str
    value: str
    domain: str


def is_relevant_cookie(cookie: RawCookie) -> bool:
    """Whether this cookie belongs to the YouTube domain family we care about.

    Unlike `document.cookie` (which the old manual-paste flow relied on), we
    read cookies via Qt's cookie store, which isn't restricted to non-HttpOnly
    cookies -- so HttpOnly cookies are deliberately NOT excluded here. Excluding
    them would risk silently breaking the whole flow if the required cookie
    ever turns out to be HttpOnly in practice.
    """
    domain = cookie.domain.lstrip(".")
    return domain == _RELEVANT_DOMAIN_SUFFIX or domain.endswith("." + _RELEVANT_DOMAIN_SUFFIX)


def has_required_cookie(cookies) -> bool:
    return any(c.name == REQUIRED_COOKIE_NAME and is_relevant_cookie(c) for c in cookies)


def build_cookie_header(cookies) -> str:
    """Builds a `document.cookie`-format string ("name1=value1; name2=value2")
    from an iterable of RawCookie, deduped by name (last write wins), in
    insertion order, restricted to relevant-domain cookies.
    """
    relevant: dict[str, str] = {}
    for cookie in cookies:
        if is_relevant_cookie(cookie):
            relevant[cookie.name] = cookie.value
    return "; ".join(f"{name}={value}" for name, value in relevant.items())
