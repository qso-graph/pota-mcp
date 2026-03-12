"""POTA API client — all public endpoints, no authentication required."""

from __future__ import annotations

import json
import math
import os
import threading
import time
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

_MOCK_SPOTS = [
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
    },
]

_MOCK_PARK_INFO = {
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
}

_MOCK_PARK_STATS = {
    "reference": "US-0001",
    "attempts": 562,
    "activations": 496,
    "contacts": 17288,
}

_MOCK_USER_STATS = {
    "callsign": "K4SWL",
    "name": "Thomas Witherspoon",
    "activator": {"activations": 558, "parks": 129, "qsos": 12638},
    "hunter": {"parks": 1455, "qsos": 2597},
    "awards": 41,
    "endorsements": 123,
}

_MOCK_SCHEDULED = [
    {
        "scheduledActivationId": 12345,
        "activator": "N3VEM",
        "name": "Shenandoah",
        "reference": "US-0058",
        "locationDesc": "US-VA",
        "activityDate": "2026-03-05",
        "startTime": "1400",
        "endTime": "1800",
        "frequencies": "14.062, 7.030",
        "comment": "CW only, weather permitting",
    },
]

_MOCK_LOCATION_PARKS = [
    {
        "reference": "US-4567",
        "name": "Boise National Forest",
        "latitude": 43.617,
        "longitude": -115.993,
        "grid4": "DN13",
        "grid6": "DN13la",
        "parktypeDesc": "National Forest",
        "activations": 12,
        "contacts": 456,
    },
    {
        "reference": "US-4568",
        "name": "Lucky Peak State Park",
        "latitude": 43.531,
        "longitude": -116.048,
        "grid4": "DN13",
        "grid6": "DN13lm",
        "parktypeDesc": "State Park",
        "activations": 5,
        "contacts": 187,
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
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
        cached = self._cache_get(key)
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
            if location and spot.get("locationDesc", "") != location.upper():
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
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = dict(_MOCK_PARK_INFO)
        else:
            data = self._get_json(f"{_BASE}/park/{urllib.parse.quote(ref)}")

        if not data:
            return {"reference": ref, "error": "Not found"}

        self._cache_set(key, data, _PARK_TTL)
        return data

    def park_stats(self, reference: str) -> dict[str, Any]:
        """Get activation/QSO counts for a park."""
        ref = reference.upper()
        key = f"park_stats:{ref}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = dict(_MOCK_PARK_STATS)
        else:
            data = self._get_json(f"{_BASE}/park/stats/{urllib.parse.quote(ref)}")

        if not data:
            return {"reference": ref, "error": "Not found"}

        self._cache_set(key, data, _STATS_TTL)
        return data

    def user_stats(self, callsign: str) -> dict[str, Any]:
        """Get activator/hunter stats by callsign."""
        call = callsign.upper()
        key = f"user:{call}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        if _is_mock():
            data = dict(_MOCK_USER_STATS)
        else:
            data = self._get_json(f"{_BASE}/stats/user/{urllib.parse.quote(call)}")

        if not data:
            return {"callsign": call, "error": "Not found"}

        self._cache_set(key, data, _STATS_TTL)
        return data

    def scheduled(self) -> list[dict[str, Any]]:
        """Get upcoming scheduled activations."""
        key = "scheduled"
        cached = self._cache_get(key)
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
        cached = self._cache_get(key)
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

    def nearby_parks(
        self,
        location: str,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Find POTA parks near a point within a location."""
        parks = self.location_parks(location)
        nearby = []
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
                nearby.append(entry)
        nearby.sort(key=lambda p: p["distance_km"])
        return nearby[:limit]
