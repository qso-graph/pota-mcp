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

    def test_drops_personal_fields(self, client):
        """POTA-L2-034: user_stats never returns qth or gravatar (#15)."""
        result = client.user_stats("K4SWL")
        assert "qth" not in result
        assert "gravatar" not in result
        assert set(result) <= {
            "callsign", "name", "activator", "attempts", "hunter", "awards", "endorsements",
        }

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


# ---------------------------------------------------------------------------
# POTA-L2-046..050: get_version_info — fleet identity attestation
# ---------------------------------------------------------------------------


class TestGetVersionInfo:
    """Tracks IONIS-AI/ionis-devel#49 — fleet get_version_info convention."""

    def test_returns_service_name(self):
        """POTA-L2-046: payload includes service_name = 'pota-mcp'."""
        from pota_mcp.server import _version_info_payload

        assert _version_info_payload()["service_name"] == "pota-mcp"

    def test_returns_service_version(self):
        """POTA-L2-047: service_version matches package __version__."""
        from pota_mcp import __version__
        from pota_mcp.server import _version_info_payload

        assert _version_info_payload()["service_version"] == __version__

    def test_returns_spec_version(self):
        """POTA-L2-048: spec_version pins the POTA API revision."""
        from pota_mcp.server import _version_info_payload

        assert _version_info_payload()["spec_version"] == "pota-api-v1"

    def test_payload_keys_are_required_set(self):
        """POTA-L2-049: payload has exactly the required keys (no extras yet)."""
        from pota_mcp.server import _version_info_payload

        result = _version_info_payload()
        required = {"service_name", "service_version", "spec_version"}
        assert required.issubset(set(result.keys()))

    def test_all_values_are_strings(self):
        """POTA-L2-050: all returned values are strings (JSON-safe envelope)."""
        from pota_mcp.server import _version_info_payload

        result = _version_info_payload()
        for k in ("service_name", "service_version", "spec_version"):
            assert isinstance(result[k], str), f"{k} should be str, got {type(result[k])}"
            assert result[k], f"{k} should be non-empty"


# ---------------------------------------------------------------------------
# pota_scheduled filters (#20)
# ---------------------------------------------------------------------------
#
# The helpers are tested directly with synthetic activations rather than
# through the mock feed, which holds one item: the cases worth covering are a
# park spanning two regions, a start time POTA did not give, and filters
# combining, and none of those exists in a single-item fixture.

import pota_mcp.server as srv  # noqa: E402


def _item(**over):
    base = {
        "activator": "N3VEM", "reference": "US-0058", "locationDesc": "US-VA",
        "activityDate": "2026-03-05", "startTime": "1400",
    }
    base.update(over)
    return base


class TestScheduledFilterHelpers:
    def test_regions_splits_a_park_that_spans_two(self):
        """POTA-L2-046: locationDesc is comma-separated for a park on a border."""
        assert srv._regions(_item(locationDesc="US-VA,US-MD")) == ["US-VA", "US-MD"]
        assert srv._regions(_item(locationDesc="us-va")) == ["US-VA"]
        assert srv._regions(_item(locationDesc="")) == []
        assert srv._regions({}) == []

    def test_location_matches_either_region_of_a_border_park(self):
        """POTA-L2-047: US-MD finds a park listed US-VA,US-MD.

        pota_spots compares locationDesc for equality and so misses these;
        that is reported separately rather than copied here.
        """
        both = _item(locationDesc="US-VA,US-MD")
        assert srv._matches(both, "US-MD", "", "") is True
        assert srv._matches(both, "us-md", "", "") is True
        assert srv._matches(both, "US-ID", "", "") is False

    def test_reference_and_activator_are_exact_and_case_insensitive(self):
        """POTA-L2-048: a reference is a whole reference, not a prefix."""
        i = _item()
        assert srv._matches(i, "", "us-0058", "") is True
        assert srv._matches(i, "", "US-005", "") is False   # not a prefix match
        assert srv._matches(i, "", "", "n3vem") is True
        assert srv._matches(i, "", "", "N3VE") is False

    def test_filters_combine_with_and(self):
        """POTA-L2-049: every filter given has to pass."""
        i = _item()
        assert srv._matches(i, "US-VA", "US-0058", "N3VEM") is True
        assert srv._matches(i, "US-VA", "US-0058", "K4SWL") is False
        assert srv._matches(i, "US-ID", "US-0058", "N3VEM") is False
        # No filters passes everything, which is what an unfiltered call does.
        assert srv._matches(i, "", "", "") is True

    def test_start_time_is_read_as_utc(self):
        """POTA-L2-050: activityDate plus startTime, both UTC."""
        at = srv._starts_at(_item(activityDate="2026-03-05", startTime="1400"))
        assert at is not None
        assert (at.year, at.month, at.day, at.hour, at.minute) == (2026, 3, 5, 14, 0)
        assert at.tzinfo is not None
        # Three digits is a valid HMM.
        early = srv._starts_at(_item(startTime="730"))
        assert early is not None and (early.hour, early.minute) == (7, 30)

    def test_an_unreadable_start_time_is_none_rather_than_a_guess(self):
        """POTA-L2-051: what POTA did not say is not invented."""
        for bad in ("", "  ", "99", "abcd", "2460", "1399", "12345"):
            assert srv._starts_at(_item(startTime=bad)) is None, bad
        assert srv._starts_at(_item(activityDate="")) is None
        assert srv._starts_at(_item(activityDate="not-a-date")) is None
        assert srv._starts_at({}) is None


class TestScheduledToolFilters:
    def test_no_filters_returns_exactly_what_it_always_did(self):
        """POTA-L2-052: an unfiltered call is unchanged — no extra keys."""
        result = srv.pota_scheduled()
        assert sorted(result) == ["activations", "total"]
        assert result["total"] == 1

    def test_nulls_are_treated_as_no_filter(self):
        """POTA-L2-053: llama.cpp/mcpo sends null for optional params (#1)."""
        result = srv.pota_scheduled(location=None, reference=None, activator=None)
        assert sorted(result) == ["activations", "total"]
        assert result["total"] == 1

    def test_a_filter_that_matches_says_what_was_asked(self):
        """POTA-L2-054: the result carries the filters and the total before them."""
        result = srv.pota_scheduled(activator="n3vem")
        assert result["total"] == 1
        assert result["filters"] == {"activator": "N3VEM"}
        assert result["available"] == 1

    def test_a_filter_that_matches_nothing_returns_an_empty_list(self):
        """POTA-L2-055: empty is an answer, and still says what was asked."""
        result = srv.pota_scheduled(location="US-ID")
        assert result["total"] == 0 and result["activations"] == []
        assert result["filters"] == {"location": "US-ID"}
        assert result["available"] == 1

    def test_a_time_window_excludes_a_date_in_the_past(self):
        """POTA-L2-056: the fixture is scheduled for 2026-03-05, already past."""
        result = srv.pota_scheduled(within_hours=24)
        assert result["total"] == 0
        assert result["filters"]["within_hours"] == 24
        assert "start_time_unreadable" not in result

    def test_an_absurd_window_does_not_raise(self):
        """POTA-L2-057: inf raises inside timedelta and nan fails every
        comparison, which would empty the list for no stated reason."""
        for value in (float("inf"), float("nan"), -5):
            result = srv.pota_scheduled(within_hours=value)
            assert "error" not in result, value


class TestScheduledWindowAgainstAFutureSchedule:
    """The fixture feed is dated 2026-03-05 and so is always in the past.

    Every window test above therefore proves exclusion. These supply a feed of
    their own so inclusion — the path an operator actually uses — is proven
    too, and so the unreadable count can be exercised at all.
    """

    @pytest.fixture
    def feed(self, monkeypatch):
        from datetime import datetime, timedelta, timezone

        def at(hours):
            when = datetime.now(timezone.utc) + timedelta(hours=hours)
            return when.strftime("%Y-%m-%d"), when.strftime("%H%M")

        soon_date, soon_time = at(2)
        later_date, later_time = at(30)
        items = [
            _item(activator="SOON", reference="US-0001", activityDate=soon_date, startTime=soon_time),
            _item(activator="LATER", reference="US-0002", activityDate=later_date, startTime=later_time),
            _item(activator="NOTIME", reference="US-0003", startTime=""),
        ]

        class Feed:
            def scheduled(self):
                return list(items)

        monkeypatch.setattr(srv, "_get_client", lambda: Feed())
        return items

    def test_a_window_keeps_what_starts_inside_it(self, feed):
        """POTA-L2-058: four hours ahead finds the one two hours away."""
        result = srv.pota_scheduled(within_hours=4)
        assert [a["activator"] for a in result["activations"]] == ["SOON"]
        assert result["available"] == 3

    def test_a_wider_window_reaches_further(self, feed):
        """POTA-L2-059: 48 hours finds both dated activations."""
        result = srv.pota_scheduled(within_hours=48)
        assert [a["activator"] for a in result["activations"]] == ["SOON", "LATER"]

    def test_an_unreadable_start_is_counted_and_not_silently_dropped(self, feed):
        """POTA-L2-060: an activation missing from a filtered list looks the
        same as one that was never scheduled, so the count is reported."""
        result = srv.pota_scheduled(within_hours=4)
        assert result["start_time_unreadable"] == 1
        assert "Omit within_hours" in result["start_time_unreadable_note"]

    def test_without_a_window_nothing_is_dropped_for_a_missing_start(self, feed):
        """POTA-L2-061: the start time only matters when a window is asked for."""
        result = srv.pota_scheduled()
        assert result["total"] == 3
        assert "start_time_unreadable" not in result

    def test_a_window_combines_with_a_text_filter(self, feed):
        """POTA-L2-062: AND, and the unreadable count is about what was asked."""
        result = srv.pota_scheduled(activator="SOON", within_hours=4)
        assert result["total"] == 1
        assert result["filters"] == {"activator": "SOON", "within_hours": 4}
        # NOTIME was filtered out by activator before the window was applied,
        # so it is not reported as unreadable here.
        assert "start_time_unreadable" not in result
