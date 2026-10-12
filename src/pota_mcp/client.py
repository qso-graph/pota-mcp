"""POTA API client — all public endpoints, no authentication required."""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import __version__

_BASE = "https://api.pota.app"

# Cache TTLs
_SPOTS_TTL = 60.0  # 1 minute
_PARK_TTL = 86400.0  # 24 hours
_STATS_TTL = 3600.0  # 1 hour
_SCHEDULED_TTL = 300.0  # 5 minutes
_LOCATION_TTL = 3600.0  # 1 hour

# Rate limiting: 100ms minimum between requests
_MIN_DELAY = 0.1


def _is_mock() -> bool:
    return os.getenv("POTA_MCP_MOCK") == "1"


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_SPOTS: list[dict[str, Any]] = [
    {
        "spotId": 47944496,
        "activator": "K4SWL",
        "frequency": "14062.5",
        "mode": "CW",
        "reference": "US-0062",
        "name": "Blue Ridge Parkway",
        "locationDesc": "US-NC",
        "grid4": "EM85",
        "grid6": "EM85qv",
        "latitude": 35.565,
        "longitude": -82.485,
        "spotTime": "2026-03-04T20:08:51",
        "spotter": "K4SWL",
        "source": "Ham2K Portable Logger",
        "comments": "CW up 2",
        "count": 23,
        "expire": 619,
        # Both are null on a live row and present on every one of them (#32).
        "parkName": None,
        "invalid": None,
    },
    {
        "spotId": 47944497,
        "activator": "KI7MT",
        "frequency": "14074.0",
        "mode": "FT8",
        "reference": "US-4567",
        "name": "Boise National Forest",
        "locationDesc": "US-ID",
        "grid4": "DN13",
        "grid6": "DN13la",
        "latitude": 43.617,
        "longitude": -115.993,
        "spotTime": "2026-03-04T20:15:30",
        "spotter": "W7RN",
        "source": "POTA App",
        "comments": "",
        "count": 8,
        "expire": 1200,
        "parkName": None,
        "invalid": None,
    },
]

_MOCK_PARK_INFO: dict[str, Any] = {
    "reference": "US-0001",
    "name": "Acadia",
    "latitude": 44.31,
    "longitude": -68.2034,
    "grid4": "FN54",
    "grid6": "FN54vh",
    "parktypeDesc": "National Park",
    "locationDesc": "US-ME",
    "locationName": "Maine",
    "entityName": "United States of America",
    "entityId": 291,
    "accessMethods": "Automobile,Boat,Foot",
    "activationMethods": "Automobile,Cabin,Campground,Pedestrian,Shelter",
    "agencies": "National Park Service",
    "website": "https://www.nps.gov/acad/index.htm",
    "firstActivator": "K8ZT",
    "firstActivationDate": "2010-06-26",
    # Also on a live row (#32). No tool reads these; they are here so the
    # fixture is the response, and so a tool written against one of them is
    # written against something that exists.
    "parkId": 1,
    "parktypeId": 41,
    "referencePrefix": "US",
    "active": 1,
    "entityDeleted": 0,
    "agencyURLs": "https://www.nps.gov/index.htm",
    "parkURLs": "https://www.nps.gov/acad/index.htm",
    "parkComments": None,
    "accessibility": None,
    "sensitivity": None,
    "createdByAdmin": None,
}

_MOCK_PARK_STATS: dict[str, Any] = {
    "reference": "US-0001",
    "attempts": 562,
    "activations": 496,
    "contacts": 17288,
}

_MOCK_USER_STATS: dict[str, Any] = {
    "callsign": "K4SWL",
    "name": "Thomas Witherspoon",
    # POTA does not send these today. They stay in the fixture on purpose: they
    # are what proves _USER_STATS_FIELDS drops them, and the day POTA sends
    # them again that proof has to still hold (#32).
    "qth": "123 Example Road",
    "gravatar": "0123456789abcdef0123456789abcdef",
    "activator": {"activations": 558, "parks": 129, "qsos": 12638},
    # An object of the same shape as `activator`, not a count: activations
    # tried against activations completed.
    "attempts": {"activations": 573, "parks": 129, "qsos": 12638},
    "hunter": {"parks": 1455, "qsos": 2597},
    "awards": 41,
    "endorsements": 123,
}

# Fields of /stats/user/{call} that pota_user_stats returns. Anything else POTA adds is
# dropped: qso-graph tools don't republish personal details (qth can hold an address, and
# gravatar is a hash of the user's email address).
_USER_STATS_FIELDS = (
    "callsign",
    "name",
    "activator",
    "attempts",
    "hunter",
    "awards",
    "endorsements",
)

# A POTA reference: an entity prefix, a hyphen, a number. `US-0062`, `JP-0123`,
# `CU-0332`, `G-0001`, and prefixes carry digits too — `9A`, `3B8`, `4U1A`.
#
# Deliberately loose about the prefix and strict about the shape. POTA adds
# entities, and a pattern that enumerated prefixes would reject a real park the
# day one is added; what this rejects is input that is not a reference at all.
# `urllib.parse.quote` already stops a path escaping the URL, so this is about
# answering "that is not a park reference" instead of passing it on and
# relaying a 404.
_REFERENCE = re.compile(r"^[A-Z0-9]{1,8}-[0-9]{1,6}$")


def valid_reference(reference: str) -> bool:
    """Whether this looks like a POTA park reference."""
    return bool(_REFERENCE.match(str(reference).strip().upper()))


def regions(item: dict[str, Any]) -> list[str]:
    """The location codes a park is in, normalised.

    POTA's `locationDesc` is comma-separated for a park that spans regions. The
    North Country Trail is `US-MI,US-MN,US-ND,US-NY,US-OH,US-PA,US-VT,US-WI`;
    on the live spot feed about one spot in twenty carries more than one code.
    So a park belongs to a region when the code is *among* its codes, never
    when it equals the whole field (#27).

    Both sides are upper-cased here. The comparison this replaced normalised
    only the filter, so a single-region park would also have failed to match if
    POTA ever returned the field in another case.
    """
    return [
        part.strip().upper()
        for part in str(item.get("locationDesc", "")).split(",")
        if part.strip()
    ]


# From the live endpoint, GET /park/activations/US-0062?count=N, 2026-10-10.
_MOCK_PARK_ACTIVATIONS: list[dict[str, Any]] = [
    {
        "activeCallsign": "KD0JYV", "qso_date": "20260826", "totalQSOs": 12,
        "qsosCW": 0, "qsosDATA": 12, "qsosPHONE": 0, "locationDesc": "US-NY",
    },
    {
        "activeCallsign": "KD2WZW", "qso_date": "20260814", "totalQSOs": 41,
        "qsosCW": 20, "qsosDATA": 0, "qsosPHONE": 21, "locationDesc": "US-NY",
    },
]

# From the live endpoint, GET /park/leaderboard/{reference}, 2026-10-10. POTA
# returns three boards of five, each row a callsign and a count.
_MOCK_PARK_LEADERBOARD: dict[str, Any] = {
    "activations": [
        {"callsign": "KD2WZW", "count": 5},
        {"callsign": "N1NDN", "count": 3},
    ],
    "activator_qsos": [
        {"callsign": "KD2WZW", "count": 189},
        {"callsign": "N1NDN", "count": 152},
    ],
    "hunter_qsos": [
        {"callsign": "N4CD", "count": 44},
        {"callsign": "AF2V", "count": 31},
    ],
}

# The field set GET /activation actually returns, checked against the live
# endpoint (#32). What was here was invented, and three of its fields do not
# exist: `scheduledActivationId` (POTA sends `scheduledActivitiesId`),
# `activityDate` (POTA sends a `startDate`/`endDate` range) and `comment`
# (POTA sends `comments`). `startTime` was `HHMM`; POTA sends `HH:MM`.
#
# That last pair is why this fixture mattered: pota_scheduled's `within_hours`
# filter read `activityDate` and required four digits, so against the real API
# it could never read a start time and discarded every activation as
# unreadable. Mock tests passed because the fixture carried the fields the code
# expected rather than the fields POTA sends.
#
# A POTA schedule entry is a date range plus a daily UTC window: a one-day
# activation has startDate == endDate, and a standing one runs to a later
# endDate with the same startTime each day. `activityStart`/`activityEnd` are
# null on every live row seen, so nothing reads them.
_MOCK_SCHEDULED: list[dict[str, Any]] = [
    {
        "scheduledActivitiesId": 141809,
        "schedulerUserId": 87305,
        "activator": "N3VEM",
        "name": "Shenandoah",
        "reference": "US-0058",
        "locationDesc": "US-VA",
        "startDate": "2026-03-05",
        "endDate": "2026-03-05",
        "startTime": "14:00",
        "endTime": "18:00",
        "activityStart": None,
        "activityEnd": None,
        "frequencies": "20 meter",
        "comments": "CW only, weather permitting",
    },
]

# The field set GET /location/parks/{loc} actually returns, checked against the
# live endpoint (#32). It is not the set this fixture used to carry:
#
#   was:  activations  contacts  grid4  grid6  latitude  longitude  name
#         parktypeDesc  reference
#   live: activations  attempts  grid  latitude  locationDesc  longitude  name
#         notes  qsos  reference  website
#
# `contacts` is `qsos` live, `grid4`/`grid6` is one `grid`, `parktypeDesc` is not
# sent at all, and `attempts`, `locationDesc`, `notes` and `website` were missing.
# Two of those matter to tools that already exist: `attempts` is how
# pota_rare_parks_near tells a park nobody has finished from one nobody has tried
# (#19), and `locationDesc` is what the region filter reads (#27). Both had to
# bring feeds of their own because this fixture could not stand in for the API.
#
# The two parks and their coordinates are unchanged, so the distance and ordering
# tests still measure what they measured; only the shape is corrected.
_MOCK_LOCATION_PARKS: list[dict[str, Any]] = [
    {
        "reference": "US-4567",
        "name": "Boise National Forest",
        "latitude": 43.617,
        "longitude": -115.993,
        "grid": "DN13la",
        "locationDesc": "US-ID",
        "activations": 12,
        "attempts": 14,
        "qsos": 456,
        "notes": "",
        "website": "https://www.fs.usda.gov/boise",
    },
    {
        "reference": "US-4568",
        "name": "Lucky Peak State Park",
        "latitude": 43.531,
        "longitude": -116.048,
        "grid": "DN13lm",
        "locationDesc": "US-ID",
        "activations": 5,
        "attempts": 5,
        "qsos": 187,
        "notes": "",
        "website": "https://parksandrecreation.idaho.gov/parks/lucky-peak/",
    },
]


class POTAClient:
    """POTA API client with rate limiting and caching."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_request: float = 0.0
        self._cache: dict[str, tuple[float, Any]] = {}

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires, value = entry
        if time.monotonic() > expires:
            del self._cache[key]
            return None
        return value

    def _cache_set(self, key: str, value: Any, ttl: float) -> None:
        self._cache[key] = (time.monotonic() + ttl, value)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < _MIN_DELAY:
                time.sleep(_MIN_DELAY - elapsed)
            self._last_request = time.monotonic()

    def _get_json(self, url: str) -> Any:
        """HTTP GET, return parsed JSON."""
        self._rate_limit()
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", f"pota-mcp/{__version__}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            # Named, because since #39 this message is what the client sees as
            # the tool's error. urllib's own text is "<urlopen error [Errno 61]
            # Connection refused>", which does not say what was being reached,
            # so a model reading it cannot tell a POTA outage from a bug here.
            raise RuntimeError(f"POTA API request failed ({url}): {e}") from e
        if not body or body.strip() == "":
            return None
        return json.loads(body)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def spots(
        self,
        band: str | None = None,
        mode: str | None = None,
        location: str | None = None,
        program: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get current activator spots."""
        key = f"spots:{band}:{mode}:{location}:{program}"
        cached: list[dict[str, Any]] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = list(_MOCK_SPOTS)
        else:
            data = self._get_json(f"{_BASE}/spot/activator") or []

        # Client-side filtering
        results = []
        for spot in data:
            if band and not self._match_band(spot.get("frequency", ""), band):
                continue
            if mode and spot.get("mode", "").upper() != mode.upper():
                continue
            if location and location.upper() not in regions(spot):
                continue
            if program and not spot.get("reference", "").startswith(program.upper()):
                continue
            results.append(spot)

        self._cache_set(key, results, _SPOTS_TTL)
        return results

    @staticmethod
    def _match_band(freq_str: str, band: str) -> bool:
        """Check if a frequency string matches a band name like '20m'."""
        try:
            freq_mhz = float(freq_str) / 1000.0 if float(freq_str) > 1000 else float(freq_str)
        except (ValueError, TypeError):
            return False
        band_ranges = {
            "160m": (1.8, 2.0), "80m": (3.5, 4.0), "60m": (5.3, 5.4),
            "40m": (7.0, 7.3), "30m": (10.1, 10.15), "20m": (14.0, 14.35),
            "17m": (18.068, 18.168), "15m": (21.0, 21.45), "12m": (24.89, 24.99),
            "10m": (28.0, 29.7), "6m": (50.0, 54.0), "2m": (144.0, 148.0),
        }
        lo, hi = band_ranges.get(band.lower(), (0, 0))
        return lo <= freq_mhz <= hi

    def park_info(self, reference: str) -> dict[str, Any]:
        """Get park details by reference code."""
        ref = reference.upper()
        key = f"park:{ref}"
        cached: dict[str, Any] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = dict(_MOCK_PARK_INFO)
        else:
            data = self._get_json(f"{_BASE}/park/{urllib.parse.quote(ref)}")

        if not data:
            # Raised, not returned: this was always a failure, said in a payload
            # the protocol could not see. A caller cannot tell "no such park"
            # from "here are the park's details" when both arrive as success.
            raise LookupError(
                f"POTA has no park {ref}. References look like US-0062."
            )

        self._cache_set(key, data, _PARK_TTL)
        return data

    def park_stats(self, reference: str) -> dict[str, Any]:
        """Get activation/QSO counts for a park."""
        ref = reference.upper()
        key = f"park_stats:{ref}"
        cached: dict[str, Any] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = dict(_MOCK_PARK_STATS)
        else:
            data = self._get_json(f"{_BASE}/park/stats/{urllib.parse.quote(ref)}")

        if not data:
            # Raised, not returned: this was always a failure, said in a payload
            # the protocol could not see. A caller cannot tell "no such park"
            # from "here are the park's details" when both arrive as success.
            raise LookupError(
                f"POTA has no park {ref}. References look like US-0062."
            )

        self._cache_set(key, data, _STATS_TTL)
        return data

    def park_activations(self, reference: str, count: int = 10) -> list[dict[str, Any]]:
        """Recent activations of a park, most recent first.

        `count` is passed to POTA and is part of the cache key, so asking for
        more than was cached fetches rather than returning a short answer.
        """
        ref = reference.strip().upper()
        key = f"park_activations:{ref}:{count}"
        cached: list[dict[str, Any]] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = list(_MOCK_PARK_ACTIVATIONS)[:count]
        else:
            data = self._get_json(
                f"{_BASE}/park/activations/{urllib.parse.quote(ref)}?count={count}"
            ) or []

        self._cache_set(key, data, _STATS_TTL)
        return data

    # The boards POTA publishes for a park. Named here rather than read off the
    # response so a board POTA adds later is not passed on without anybody
    # deciding to, which is the same rule the projection below follows.
    LEADERBOARDS = ("activations", "activator_qsos", "hunter_qsos")

    def park_leaderboard(self, reference: str, limit: int = 10) -> dict[str, Any]:
        """The callsigns with the most activations and QSOs at a park.

        Each row is reduced to a callsign and a count, and nothing else.
        POTA's user endpoint already had to have `qth` — which can hold a
        street address — and `gravatar`, a hash of an email address, stripped
        out of it (#15). Trusting a response to carry only what it carries
        today is how that happened, so the shape is chosen here rather than
        relayed.
        """
        ref = reference.strip().upper()
        key = f"park_leaderboard:{ref}:{limit}"
        cached: dict[str, Any] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            raw = {k: list(v) for k, v in _MOCK_PARK_LEADERBOARD.items()}
        else:
            raw = self._get_json(f"{_BASE}/park/leaderboard/{urllib.parse.quote(ref)}") or {}

        boards: dict[str, Any] = {}
        for name in self.LEADERBOARDS:
            rows = raw.get(name) or []
            boards[name] = [
                {
                    "callsign": str(row.get("callsign", "")).upper(),
                    "count": row.get("count", 0),
                }
                for row in rows[:limit]
                if isinstance(row, dict) and row.get("callsign")
            ]

        self._cache_set(key, boards, _STATS_TTL)
        return boards

    def user_stats(self, callsign: str) -> dict[str, Any]:
        """Get activator/hunter stats by callsign."""
        call = callsign.upper()
        key = f"user:{call}"
        cached: dict[str, Any] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = dict(_MOCK_USER_STATS)
        else:
            data = self._get_json(f"{_BASE}/stats/user/{urllib.parse.quote(call)}")

        if not data:
            # As above. POTA holding no record for a callsign is not the same
            # answer as that operator having zero activations, and the old shape
            # could not express the difference either.
            raise LookupError(f"POTA has no record for {call}.")

        data = {k: data[k] for k in _USER_STATS_FIELDS if k in data}
        self._cache_set(key, data, _STATS_TTL)
        return data

    def scheduled(self) -> list[dict[str, Any]]:
        """Get upcoming scheduled activations."""
        key = "scheduled"
        cached: list[dict[str, Any]] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = list(_MOCK_SCHEDULED)
        else:
            data = self._get_json(f"{_BASE}/activation") or []

        self._cache_set(key, data, _SCHEDULED_TTL)
        return data

    def location_parks(self, location: str) -> list[dict[str, Any]]:
        """Get all parks in a location (state/province)."""
        loc = location.upper()
        key = f"location:{loc}"
        cached: list[dict[str, Any]] | None = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = list(_MOCK_LOCATION_PARKS)
        else:
            data = self._get_json(
                f"{_BASE}/location/parks/{urllib.parse.quote(loc)}"
            ) or []

        self._cache_set(key, data, _LOCATION_TTL)
        return data

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance in km between two points."""
        R = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _parks_within(
        self,
        location: str,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[dict[str, Any]]:
        """Every park in the location within the radius, each with distance_km.

        Uncapped on purpose. Both callers below cap, but by different things —
        distance for the nearest, activations for the rarest — and a list
        already cut to the twenty-five nearest cannot answer "which park near
        me has never been activated" if that park is fortieth nearest.

        One call to POTA either way: /location/parks/{loc} carries each park's
        activations, attempts and qsos, so no per-park request is needed.
        """
        parks = self.location_parks(location)
        within = []
        for park in parks:
            plat = park.get("latitude")
            plon = park.get("longitude")
            if plat is None or plon is None:
                continue
            try:
                dist = self._haversine(latitude, longitude, float(plat), float(plon))
            except (ValueError, TypeError):
                continue
            if dist <= radius_km:
                entry = dict(park)
                entry["distance_km"] = round(dist, 1)
                within.append(entry)
        return within

    def nearby_parks(
        self,
        location: str,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Find POTA parks near a point within a location."""
        nearby = self._parks_within(location, latitude, longitude, radius_km)
        nearby.sort(key=lambda p: p["distance_km"])
        return nearby[:limit]

    def rare_parks_near(
        self,
        location: str,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Parks near a point, least activated first, then nearest.

        Each entry gains `never_activated`. A park with attempts but no
        activations is a different thing again — somebody has been and not made
        the ten contacts — and `attempts` is already in POTA's park data, so it
        comes through untouched for a caller who cares.
        """
        candidates = self._parks_within(location, latitude, longitude, radius_km)
        for park in candidates:
            try:
                activations = int(park.get("activations") or 0)
            except (TypeError, ValueError):
                activations = 0
            park["never_activated"] = activations == 0
        candidates.sort(key=lambda p: (int(p.get("activations") or 0), p["distance_km"]))
        return candidates[:limit]
