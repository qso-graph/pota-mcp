"""L3 live integration tests for pota-mcp.

These tests hit the real POTA API (api.pota.app) and validate
responses against known-good reference values.

Run with: pytest tests/test_live.py --live
"""

import os

import pytest

from pota_mcp.client import POTAClient

# Ensure mock mode is OFF for live tests
os.environ.pop("POTA_MCP_MOCK", None)

# Known-good reference values
KNOWN_PARK = "US-0001"  # Acadia National Park
KNOWN_LOCATION = "US-ME"  # Maine
ACADIA_LAT = 44.338
ACADIA_LON = -68.273
KNOWN_USER = "K4SWL"  # One of the most active POTA operators


@pytest.fixture(scope="module")
def client():
    """Shared POTAClient instance for all live tests."""
    return POTAClient()


# POTA-L3-001: spots returns a list with expected fields
@pytest.mark.live
def test_spots_live(client):
    """POTA-L3-001: spots() returns list; non-empty spots have required fields."""
    result = client.spots()
    assert isinstance(result, list), "spots() must return a list"
    if len(result) > 0:
        spot = result[0]
        for field in ("activator", "frequency", "mode", "reference"):
            assert field in spot, f"Spot missing required field: {field}"
        # Activator should be a non-empty callsign string
        assert isinstance(spot["activator"], str) and len(spot["activator"]) > 0


# POTA-L3-002: park_info returns Acadia details
@pytest.mark.live
def test_park_info_live(client):
    """POTA-L3-002: park_info('US-0001') returns Acadia with correct fields."""
    result = client.park_info(KNOWN_PARK)
    assert "error" not in result, f"park_info returned error: {result}"
    assert "Acadia" in result.get("name", ""), f"Expected 'Acadia' in name, got: {result.get('name')}"
    assert "latitude" in result, "Missing latitude"
    assert "longitude" in result, "Missing longitude"
    assert "grid4" in result, "Missing grid4"


# POTA-L3-003: park_info reference matches request
@pytest.mark.live
def test_park_info_reference_live(client):
    """POTA-L3-003: park_info response reference matches requested park."""
    result = client.park_info(KNOWN_PARK)
    assert result.get("reference") == KNOWN_PARK


# POTA-L3-004: park_info coordinates are plausible for Acadia
@pytest.mark.live
def test_park_info_coordinates_live(client):
    """POTA-L3-004: Acadia coordinates within reasonable bounds."""
    result = client.park_info(KNOWN_PARK)
    lat = float(result["latitude"])
    lon = float(result["longitude"])
    # Acadia is in Maine — lat ~44, lon ~-68
    assert 43.0 < lat < 45.0, f"Latitude {lat} out of range for Acadia"
    assert -70.0 < lon < -67.0, f"Longitude {lon} out of range for Acadia"


# POTA-L3-005: park_stats returns positive activations and contacts
@pytest.mark.live
def test_park_stats_live(client):
    """POTA-L3-005: park_stats('US-0001') returns activations > 0, contacts > 0."""
    result = client.park_stats(KNOWN_PARK)
    assert "error" not in result, f"park_stats returned error: {result}"
    assert result.get("activations", 0) > 0, "Acadia should have activations > 0"
    assert result.get("contacts", 0) > 0, "Acadia should have contacts > 0"


# POTA-L3-006: park_stats reference matches
@pytest.mark.live
def test_park_stats_reference_live(client):
    """POTA-L3-006: park_stats response reference matches requested park."""
    result = client.park_stats(KNOWN_PARK)
    assert result.get("reference") == KNOWN_PARK


# POTA-L3-007: user_stats returns K4SWL with activator and hunter dicts
@pytest.mark.live
def test_user_stats_live(client):
    """POTA-L3-007: user_stats('K4SWL') returns callsign with activator/hunter stats."""
    result = client.user_stats(KNOWN_USER)
    assert "error" not in result, f"user_stats returned error: {result}"
    assert result.get("callsign") == KNOWN_USER, f"Expected callsign {KNOWN_USER}, got: {result.get('callsign')}"
    assert isinstance(result.get("activator"), dict), "activator should be a dict"
    assert isinstance(result.get("hunter"), dict), "hunter should be a dict"


# POTA-L3-008: user_stats K4SWL has substantial activity
@pytest.mark.live
def test_user_stats_activity_live(client):
    """POTA-L3-008: K4SWL activator stats show significant activity."""
    result = client.user_stats(KNOWN_USER)
    activator = result.get("activator", {})
    assert activator.get("activations", 0) > 100, "K4SWL should have 100+ activations"
    assert activator.get("qsos", 0) > 1000, "K4SWL should have 1000+ QSOs"


# POTA-L3-009: scheduled returns a list with expected fields
@pytest.mark.live
def test_scheduled_live(client):
    """POTA-L3-009: scheduled() returns list; non-empty items have required fields."""
    result = client.scheduled()
    assert isinstance(result, list), "scheduled() must return a list"
    if len(result) > 0:
        item = result[0]
        for field in ("activator", "reference"):
            assert field in item, f"Scheduled item missing required field: {field}"


# POTA-L3-010: location_parks returns parks for Maine including Acadia
@pytest.mark.live
def test_location_parks_live(client):
    """POTA-L3-010: location_parks('US-ME') includes US-0001 (Acadia)."""
    result = client.location_parks(KNOWN_LOCATION)
    assert isinstance(result, list), "location_parks() must return a list"
    assert len(result) > 0, "Maine should have parks"
    references = [p.get("reference") for p in result]
    assert KNOWN_PARK in references, f"US-0001 not found in Maine parks (got {len(result)} parks)"


# POTA-L3-011: location_parks entries have park fields
@pytest.mark.live
def test_location_parks_fields_live(client):
    """POTA-L3-011: location_parks entries have reference, name, latitude, longitude."""
    result = client.location_parks(KNOWN_LOCATION)
    assert len(result) > 0
    park = result[0]
    for field in ("reference", "name", "latitude", "longitude"):
        assert field in park, f"Park entry missing field: {field}"


# POTA-L3-012: nearby_parks returns parks with distance_km, sorted by distance
@pytest.mark.live
def test_nearby_parks_live(client):
    """POTA-L3-012: nearby_parks near Acadia returns parks sorted by distance."""
    result = client.nearby_parks(KNOWN_LOCATION, ACADIA_LAT, ACADIA_LON, radius_km=100.0)
    assert isinstance(result, list), "nearby_parks() must return a list"
    assert len(result) > 0, "Should find parks near Acadia within 100 km"
    # Every entry must have distance_km
    for park in result:
        assert "distance_km" in park, "Park missing distance_km field"
        assert isinstance(park["distance_km"], (int, float)), "distance_km must be numeric"
    # Verify sorted by distance ascending
    distances = [p["distance_km"] for p in result]
    assert distances == sorted(distances), "Parks must be sorted by distance_km ascending"


# POTA-L3-013: nearby_parks includes Acadia itself (distance ~0)
@pytest.mark.live
def test_nearby_parks_includes_acadia_live(client):
    """POTA-L3-013: nearby_parks near Acadia coords should include US-0001."""
    result = client.nearby_parks(KNOWN_LOCATION, ACADIA_LAT, ACADIA_LON, radius_km=50.0)
    references = [p.get("reference") for p in result]
    assert KNOWN_PARK in references, "Acadia (US-0001) should appear in nearby parks near its own coordinates"
    # Acadia should be very close to itself
    acadia = next(p for p in result if p.get("reference") == KNOWN_PARK)
    assert acadia["distance_km"] < 10.0, f"Acadia distance from its own coords should be < 10 km, got {acadia['distance_km']}"


# POTA-L3-014: spots with band filter
@pytest.mark.live
def test_spots_band_filter_live(client):
    """POTA-L3-014: spots(band='20m') returns only 20m spots (if any)."""
    result = client.spots(band="20m")
    assert isinstance(result, list), "spots(band='20m') must return a list"
    # If there are results, all should be on 20m (14.0-14.35 MHz)
    for spot in result:
        freq = float(spot["frequency"]) / 1000.0 if float(spot["frequency"]) > 1000 else float(spot["frequency"])
        assert 14.0 <= freq <= 14.35, f"Spot frequency {freq} MHz is not on 20m"


# POTA-L3-015: case-insensitive park reference
@pytest.mark.live
def test_park_info_case_insensitive_live(client):
    """POTA-L3-015: park_info handles lowercase reference gracefully."""
    result = client.park_info("us-0001")
    assert "error" not in result, f"park_info('us-0001') returned error: {result}"
    assert result.get("reference") == KNOWN_PARK, "Reference should be normalized to uppercase"
