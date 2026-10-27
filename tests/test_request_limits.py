"""POTA's request limits: the refresh floors, and what a 429 does.

These assert the three mechanisms of guarantee 8 separately, because they were
once conflated: a refresh floor bounds how often we may ask, the spacing
constant bounds how closely two asks may land, and a 429 is POTA stating its
limit at runtime. See qso-graph-devel/planning/MCP-SECURITY-FRAMEWORK.md.
"""

from __future__ import annotations

import ssl
import urllib.error
from email.message import Message

import pytest

from pota_mcp import client as c


def _headers(**kw: str) -> Message:
    m = Message()
    for k, v in kw.items():
        m[k.replace("_", "-")] = v
    return m


def _http_error(code: int, **headers: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.pota.app/spot/activator", code, "nope", _headers(**headers), None
    )


# --- the refresh floors ----------------------------------------------------


def test_refresh_floors_are_the_agreed_figures() -> None:
    """These match QG Desktop's table; a silent change here is drift.

    Asserted because a TTL is the limit that actually decides how many requests
    a day this server can cause, and it is a one-character edit away from being
    much smaller.
    """
    assert c._SPOTS_TTL == 60.0
    assert c._PARK_TTL == 86400.0
    assert c._STATS_TTL == 86400.0
    assert c._LOCATION_TTL == 86400.0
    assert c._SCHEDULED_TTL == 300.0


def test_spacing_is_distinct_from_the_floors() -> None:
    """A gap between calls, not a staleness bound -- different magnitudes."""
    assert 0 < c._MIN_DELAY < 1.0, "spacing is sub-second"
    assert c._SPOTS_TTL >= 60.0, "the shortest floor is at least a minute"


# --- Retry-After parsing ---------------------------------------------------


@pytest.mark.parametrize(
    "header,expected",
    [
        (None, c._MIN_BACKOFF),       # absent: wait the floor, do not guess
        ("", c._MIN_BACKOFF),
        ("0", c._MIN_BACKOFF),        # a provider saying "now" still gets a floor
        ("5", c._MIN_BACKOFF),        # below the floor is raised to it
        ("300", 300.0),               # honoured as stated
        ("99999", c._MAX_BACKOFF),    # above the ceiling is capped
        ("Wed, 21 Oct 2026 07:28:00 GMT", c._MIN_BACKOFF),  # date form unparsed
        ("garbage", c._MIN_BACKOFF),
    ],
)
def test_retry_after_is_honoured_within_bounds(header: str | None, expected: float) -> None:
    assert c._retry_after(header) == expected


# --- what a 429 does -------------------------------------------------------


def test_429_raises_rate_limited_and_names_the_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> None:
        raise _http_error(429, Retry_After="120")

    monkeypatch.setattr(c.urllib.request, "urlopen", boom)
    cl = c.POTAClient()
    with pytest.raises(c.RateLimited) as e:
        cl._get_json("https://api.pota.app/spot/activator")
    assert e.value.retry_after == 120
    assert "120" in str(e.value)


def test_429_blocks_later_calls_without_asking_pota(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point of honouring the limit: the next call must not go out."""
    calls: list[str] = []

    def boom(req: object, **k: object) -> None:
        calls.append("sent")
        raise _http_error(429, Retry_After="120")

    monkeypatch.setattr(c.urllib.request, "urlopen", boom)
    cl = c.POTAClient()
    with pytest.raises(c.RateLimited):
        cl._get_json("https://api.pota.app/spot/activator")
    assert calls == ["sent"]

    # A different endpoint: the block is client-wide, as POTA's view of us is.
    with pytest.raises(c.RateLimited):
        cl._get_json("https://api.pota.app/park/US-0001")
    assert calls == ["sent"], "a second request was sent while blocked"


def test_block_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    cl = c.POTAClient()
    cl._blocked_until = 0.0  # as if the wait has passed
    seen: list[str] = []

    class Resp:
        def read(self) -> bytes:
            seen.append("sent")
            return b"[]"

        def __enter__(self) -> "Resp":
            return self

        def __exit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(c.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert cl._get_json("https://api.pota.app/spot/activator") == []
    assert seen == ["sent"]


def test_bare_503_is_an_outage_not_a_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without Retry-After a 503 is POTA being down, and must not block the client."""
    monkeypatch.setattr(
        c.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(_http_error(503))
    )
    cl = c.POTAClient()
    with pytest.raises(RuntimeError) as e:
        cl._get_json("https://api.pota.app/spot/activator")
    assert not isinstance(e.value, c.RateLimited)
    assert cl._blocked_until == 0.0


def test_503_with_retry_after_is_a_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        c.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(503, Retry_After="90")),
    )
    cl = c.POTAClient()
    with pytest.raises(c.RateLimited) as e:
        cl._get_json("https://api.pota.app/spot/activator")
    assert e.value.retry_after == 90


def test_network_failure_still_names_pota(monkeypatch: pytest.MonkeyPatch) -> None:
    """The #39 behaviour must survive: the message says what was being reached."""
    monkeypatch.setattr(
        c.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("refused")),
    )
    cl = c.POTAClient()
    with pytest.raises(RuntimeError, match="POTA API request failed"):
        cl._get_json("https://api.pota.app/spot/activator")


def test_ssl_failure_is_reported_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        c.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(ssl.SSLError("bad cert")),
    )
    cl = c.POTAClient()
    with pytest.raises(RuntimeError, match="POTA API request failed"):
        cl._get_json("https://api.pota.app/spot/activator")
