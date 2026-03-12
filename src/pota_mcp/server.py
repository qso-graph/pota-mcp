"""pota-mcp: MCP server for Parks on the Air — all public, no auth required."""

from __future__ import annotations

import sys
from typing import Any

from fastmcp import FastMCP

from . import __version__
from .client import POTAClient

mcp = FastMCP(
    "pota-mcp",
    version=__version__,
    instructions=(
        "MCP server for Parks on the Air (POTA) — live activator spots, "
        "park info, activator/hunter stats, scheduled activations. "
        "All public endpoints, no authentication required."
    ),
)

_client: POTAClient | None = None


def _get_client() -> POTAClient:
    """Get or create the shared POTA client."""
    global _client
    if _client is None:
        _client = POTAClient()
    return _client


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def pota_spots(
    band: str = "",
    mode: str = "",
    location: str = "",
    program: str = "",
) -> dict[str, Any]:
    """Get current POTA activator spots.

    Returns live spot feed with park details, grid squares, and coordinates.
    All filters are optional — omit to get all active spots.

    Args:
        band: Filter by band (e.g., 20m, 40m). Empty for all bands.
        mode: Filter by mode (e.g., CW, FT8, SSB). Empty for all modes.
        location: Filter by location code (e.g., US-ID, CA-ON). Empty for all.
        program: Filter by program prefix (e.g., US, VE, G). Empty for all.

    Returns:
        List of active spots with activator, frequency, park, grid, and coordinates.
    """
    try:
        spots = _get_client().spots(
            band=band or None,
            mode=mode or None,
            location=location or None,
            program=program or None,
        )
        return {"total": len(spots), "spots": spots}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def pota_park_info(reference: str) -> dict[str, Any]:
    """Get detailed park information by POTA reference code.

    Args:
        reference: Park reference code (e.g., US-0001, CA-5580, G-0001).

    Returns:
        Park details including name, coordinates, grid, type, location,
        access methods, agencies, website, and first activation info.
    """
    try:
        return _get_client().park_info(reference)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def pota_park_stats(reference: str) -> dict[str, Any]:
    """Get activation and QSO counts for a POTA park.

    Args:
        reference: Park reference code (e.g., US-0001).

    Returns:
        Activation attempts, successful activations, and total contacts.
    """
    try:
        return _get_client().park_stats(reference)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def pota_user_stats(callsign: str) -> dict[str, Any]:
    """Get POTA activator and hunter statistics for a callsign.

    Args:
        callsign: Callsign to look up (e.g., K4SWL, KI7MT).

    Returns:
        Activator stats (activations, parks, QSOs), hunter stats
        (parks worked, QSOs), awards, and endorsements.
    """
    try:
        return _get_client().user_stats(callsign)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def pota_scheduled() -> dict[str, Any]:
    """Get upcoming scheduled POTA activations.

    Returns:
        List of scheduled activations with activator, park, date,
        time window, planned frequencies, and comments.
    """
    try:
        items = _get_client().scheduled()
        return {"total": len(items), "activations": items}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def pota_location_parks(location: str) -> dict[str, Any]:
    """List all POTA parks in a state, province, or country.

    Args:
        location: Location code (e.g., US-ID for Idaho, CA-ON for Ontario, G for England).

    Returns:
        List of parks with reference, name, coordinates, grid, type,
        and activation/contact counts.
    """
    try:
        parks = _get_client().location_parks(location)
        return {"location": location.upper(), "total": len(parks), "parks": parks}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def pota_nearby_parks(
    location: str,
    latitude: float,
    longitude: float,
    radius_km: float = 50.0,
    limit: int = 25,
) -> dict[str, Any]:
    """Find POTA parks near a geographic point.

    Fetches all parks in the given location and filters by distance.
    Useful for finding 2-fer candidates near an activation site.

    Args:
        location: Location code (e.g., US-ID, CA-ON). Required to scope the search.
        latitude: Center point latitude (e.g., 43.617).
        longitude: Center point longitude (e.g., -115.993).
        radius_km: Search radius in km (default 50, max 500).
        limit: Maximum parks to return (default 25, max 100).

    Returns:
        Parks within radius, sorted by distance, with distance_km field added.
    """
    try:
        radius_km = min(max(radius_km, 1.0), 500.0)
        limit = min(max(limit, 1), 100)
        parks = _get_client().nearby_parks(
            location=location,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            limit=limit,
        )
        return {
            "location": location.upper(),
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "total": len(parks),
            "parks": parks,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the pota-mcp server."""
    transport = "stdio"
    port = 8006
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--transport" and i < len(sys.argv) - 1:
            transport = sys.argv[i + 1]
        if arg == "--port" and i < len(sys.argv) - 1:
            port = int(sys.argv[i + 1])

    if transport == "streamable-http":
        mcp.run(transport=transport, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
