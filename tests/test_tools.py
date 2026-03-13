"""L2 unit tests for pota-mcp — all 7 tools + helper functions.

Uses POTA_MCP_MOCK=1 for tool-level tests (no POTA API calls).
Direct unit tests on POTAClient helper methods.

Test IDs: POTA-L2-001 through POTA-L2-045
"""

from __future__ import annotations

import math
import os
import pytest

# Enable mock mode before importing anything
os.environ["POTA_MCP_MOCK"] = "1"

from pota_mcp.client import POTAClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Fresh POTAClient instance (no cache carryover)."""
    return POTAClient()


# ---------------------------------------------------------------------------
# POTA-L2-001..008: _match_band (frequency → band matching)
# ---------------------------------------------------------------------------


class TestMatchBand:
    def test_20m_in_khz(self):
        """POTA-L2-001: 14074.0 kHz → 20m match."""
        assert POTAClient._match_band("14074.0", "20m") is True

    def test_20m_in_mhz(self):
        """POTA-L2-002: 14.074 MHz → 20m match."""
        assert POTAClient._match_band("14.074", "20m") is True

    def test_40m_match(self):
        """POTA-L2-003: 7030.0 kHz → 40m match."""
        assert POTAClient._match_band("7030.0", "40m") is True

    def test_wrong_band(self):
        """POTA-L2-004: 14074 kHz does NOT match 40m."""
        assert POTAClient._match_band("14074.0", "40m") is False

    def test_invalid_frequency(self):
        """POTA-L2-005: Non-numeric frequency → False."""
        assert POTAClient._match_band("abc", "20m") is False
        assert POTAClient._match_band("", "20m") is False

    def test_all_bands(self):
        """POTA-L2-006: Representative frequencies for all HF bands."""
        cases = [
            ("1840.0", "160m"), ("3573.0", "80m"), ("5357.0", "60m"),
            ("7074.0", "40m"), ("10136.0", "30m"), ("14074.0", "20m"),
            ("18100.0", "17m"), ("21074.0", "15m"), ("24915.0", "12m"),
            ("28074.0", "10m"), ("50313.0", "6m"),
        ]
        for freq, band in cases:
            assert POTAClient._match_band(freq, band) is True, f"{freq} should match {band}"

    def test_unknown_band(self):
        """POTA-L2-007: Unknown band name → False."""
        assert POTAClient._match_band("14074.0", "99m") is False

    def test_case_insensitive_band(self):
        """POTA-L2-008: Band matching is case-insensitive."""
        assert POTAClient._match_band("14074.0", "20M") is True


# ---------------------------------------------------------------------------
# POTA-L2-010..015: _haversine (distance calculation)
# ---------------------------------------------------------------------------


class TestHaversine:
    def test_zero_distance(self):
        """POTA-L2-010: Same point → 0 km."""
        assert POTAClient._haversine(43.617, -115.993, 43.617, -115.993) == 0.0

    def test_known_distance(self):
        """POTA-L2-011: Boise→Portland ~570 km."""
        dist = POTAClient._haversine(43.617, -115.993, 45.515, -122.679)
        assert 560 < dist < 580

    def test_symmetry(self):
        """POTA-L2-012: haversine(A,B) == haversine(B,A)."""
        d1 = POTAClient._haversine(43.617, -115.993, 45.515, -122.679)
        d2 = POTAClient._haversine(45.515, -122.679, 43.617, -115.993)
        assert abs(d1 - d2) < 0.01

    def test_antipodal(self):
        """POTA-L2-013: Antipodal points ~20015 km."""
        dist = POTAClient._haversine(0.0, 0.0, 0.0, 180.0)
        assert 20000 < dist < 20100

    def test_short_distance(self):
        """POTA-L2-014: Two nearby parks ~10 km."""
        # US-4567 and US-4568 from mock data
        dist = POTAClient._haversine(43.617, -115.993, 43.531, -116.048)
        assert 5 < dist < 15


# ---------------------------------------------------------------------------
# POTA-L2-020..030: Tool mock-mode tests
# ---------------------------------------------------------------------------


class TestSpotsTool:
    def test_all_spots(self, client):
        """POTA-L2-020: spots() returns all mock spots."""
        result = client.spots()
        assert len(result) == 2

    def test_filter_by_mode(self, client):
        """POTA-L2-021: spots(mode='CW') filters correctly."""
        result = client.spots(mode="CW")
        assert len(result) == 1
        assert result[0]["activator"] == "K4SWL"

    def test_filter_by_mode_ft8(self, client):
        """POTA-L2-022: spots(mode='FT8') filters correctly."""
        result = client.spots(mode="FT8")
        assert len(result) == 1
        assert result[0]["activator"] == "KI7MT"

    def test_filter_by_band(self, client):
        """POTA-L2-023: spots(band='20m') matches both mock spots on 14 MHz."""
        result = client.spots(band="20m")
        assert len(result) == 2  # Both mock spots are on 14 MHz

    def test_filter_by_location(self, client):
        """POTA-L2-024: spots(location='US-ID') filters by location."""
        result = client.spots(location="US-ID")
        assert len(result) == 1
        assert result[0]["activator"] == "KI7MT"

    def test_filter_by_program(self, client):
        """POTA-L2-025: spots(program='US') matches US parks."""
        result = client.spots(program="US")
        assert len(result) == 2

    def test_filter_no_match(self, client):
        """POTA-L2-026: Filtering with non-matching criteria → empty."""
        result = client.spots(mode="RTTY")
        assert len(result) == 0

    def test_spot_fields(self, client):
        """POTA-L2-027: Spots have expected fields."""
        spots = client.spots()
        spot = spots[0]
        for field in ("activator", "frequency", "mode", "reference", "name", "grid4"):
            assert field in spot, f"Missing field: {field}"


class TestParkInfoTool:
    def test_returns_park(self, client):
        """POTA-L2-028: park_info returns mock park data."""
        result = client.park_info("US-0001")
        assert result["name"] == "Acadia"
        assert result["reference"] == "US-0001"

    def test_case_insensitive(self, client):
        """POTA-L2-029: park_info uppercases reference."""
        result = client.park_info("us-0001")
        assert result["reference"] == "US-0001"

    def test_park_fields(self, client):
        """POTA-L2-030: Park info has expected fields."""
        result = client.park_info("US-0001")
        for field in ("name", "latitude", "longitude", "grid4", "parktypeDesc", "locationDesc"):
            assert field in result, f"Missing field: {field}"


class TestParkStatsTool:
    def test_returns_stats(self, client):
        """POTA-L2-031: park_stats returns activation counts."""
        result = client.park_stats("US-0001")
        assert result["attempts"] == 562
        assert result["activations"] == 496
        assert result["contacts"] == 17288


class TestUserStatsTool:
    def test_returns_user(self, client):
        """POTA-L2-032: user_stats returns activator/hunter data."""
        result = client.user_stats("K4SWL")
        assert result["callsign"] == "K4SWL"
        assert "activator" in result
        assert "hunter" in result
        assert result["activator"]["activations"] == 558

    def test_uppercase_callsign(self, client):
        """POTA-L2-033: user_stats uppercases callsign."""
        result = client.user_stats("k4swl")
        assert result["callsign"] == "K4SWL"


class TestScheduledTool:
    def test_returns_scheduled(self, client):
        """POTA-L2-034: scheduled() returns activation list."""
        result = client.scheduled()
        assert len(result) == 1
        assert result[0]["activator"] == "N3VEM"

    def test_scheduled_fields(self, client):
        """POTA-L2-035: Scheduled activations have expected fields."""
        result = client.scheduled()
        item = result[0]
        for field in ("activator", "reference", "activityDate", "startTime"):
            assert field in item, f"Missing field: {field}"


class TestLocationParksTool:
    def test_returns_parks(self, client):
        """POTA-L2-036: location_parks returns park list."""
        result = client.location_parks("US-ID")
        assert len(result) == 2
        assert result[0]["reference"] == "US-4567"

    def test_uppercase_location(self, client):
        """POTA-L2-037: location_parks uppercases location."""
        result = client.location_parks("us-id")
        assert len(result) == 2


class TestNearbyParksTool:
    def test_returns_nearby(self, client):
        """POTA-L2-038: nearby_parks returns parks with distance."""
        result = client.nearby_parks("US-ID", 43.617, -115.993, radius_km=100)
        assert len(result) > 0
        for park in result:
            assert "distance_km" in park

    def test_sorted_by_distance(self, client):
        """POTA-L2-039: nearby_parks returns parks sorted by distance."""
        result = client.nearby_parks("US-ID", 43.617, -115.993, radius_km=100)
        if len(result) > 1:
            distances = [p["distance_km"] for p in result]
            assert distances == sorted(distances)

    def test_limit_respected(self, client):
        """POTA-L2-040: nearby_parks respects limit parameter."""
        result = client.nearby_parks("US-ID", 43.617, -115.993, radius_km=500, limit=1)
        assert len(result) <= 1

    def test_small_radius(self, client):
        """POTA-L2-041: Very small radius may return fewer/no parks."""
        result = client.nearby_parks("US-ID", 43.617, -115.993, radius_km=0.001)
        # Only parks within 1 meter — likely none
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# POTA-L2-042..045: Cache and edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_cache_expiry(self, client):
        """POTA-L2-042: Cache entries expire after TTL."""
        client._cache_set("test_key", "test_value", 0.01)
        assert client._cache_get("test_key") == "test_value"
        import time
        time.sleep(0.02)
        assert client._cache_get("test_key") is None

    def test_cache_miss(self, client):
        """POTA-L2-043: Cache miss returns None."""
        assert client._cache_get("nonexistent") is None

    def test_spots_cached(self, client):
        """POTA-L2-044: Second spots() call returns cached result."""
        r1 = client.spots()
        r2 = client.spots()
        assert r1 is r2

    def test_haversine_near_zero(self):
        """POTA-L2-045: Very close points → near-zero distance."""
        dist = POTAClient._haversine(43.617, -115.993, 43.6171, -115.9931)
        assert dist < 0.1  # Less than 100 meters
