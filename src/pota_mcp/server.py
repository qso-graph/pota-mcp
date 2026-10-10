"""pota-mcp: MCP server for Parks on the Air — all public, no auth required."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from . import __spec_version__, __version__
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


def _version_info_payload() -> dict[str, Any]:
    """Build the version info envelope. Pulled into a helper so tests can
    call it directly without going through the FastMCP wrapper."""
    return {
        "service_name": "pota-mcp",
        "service_version": __version__,
        "spec_version": __spec_version__,
    }


@mcp.tool()
def get_version_info() -> dict[str, Any]:
    """Get pota-mcp service version and upstream spec version.

    Returns the running PyPI version of pota-mcp and the POTA API
    revision currently in use. Use this to confirm fleet alignment
    across MCP deployments — agents can compare service_version and
    spec_version across servers to detect drift without going outside
    the MCP protocol.

    Returns:
        service_name, service_version (PyPI), and spec_version (POTA API).
    """
    return _version_info_payload()


@mcp.tool()
def pota_spots(
    band: str | None = "",
    mode: str | None = "",
    location: str | None = "",
    program: str | None = "",
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
        # Coerce None → "" (llama.cpp/mcpo sends null for optional params)
        band = band or ""
        mode = mode or ""
        location = location or ""
        program = program or ""
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


# ---------------------------------------------------------------------------
# Scheduled-activation filters (#20)
# ---------------------------------------------------------------------------
#
# Applied here rather than in the client, deliberately. `client.scheduled()`
# caches the whole feed under one key, so one cached fetch serves every
# combination of filters. `spots` takes the other route and keys its cache by
# its filters, which means a different band is a different cache entry and a
# fresh fetch.


def _regions(item: dict[str, Any]) -> list[str]:
    """The location codes an activation is in.

    POTA's `locationDesc` is comma-separated for a park that spans regions —
    one on a state line is `US-VA,US-MD` — so a park is matched when the code
    is *among* its regions rather than equal to the whole field. `pota_spots`
    compares the field for equality and so misses those parks; reported
    separately rather than copied.
    """
    return [part.strip().upper() for part in str(item.get("locationDesc", "")).split(",") if part.strip()]


def _starts_at(item: dict[str, Any]) -> datetime | None:
    """When the activation starts, in UTC, or None if POTA did not say.

    `activityDate` is `YYYY-MM-DD` and `startTime` is `HHMM`, both UTC. An
    entry whose start cannot be read is not silently dropped: the count of
    those is reported, because an activation missing from a filtered list looks
    the same as one that was never scheduled.
    """
    date, time = str(item.get("activityDate", "")), str(item.get("startTime", "")).strip()
    if not date or len(time) not in (3, 4) or not time.isdigit():
        return None
    try:
        hour, minute = int(time[:-2]), int(time[-2:])
        if hour > 23 or minute > 59:
            return None
        day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return day + timedelta(hours=hour, minutes=minute)


def _matches(
    item: dict[str, Any],
    location: str,
    reference: str,
    activator: str,
) -> bool:
    """Whether one activation passes every text filter given (AND)."""
    if location and location.upper() not in _regions(item):
        return False
    if reference and str(item.get("reference", "")).upper() != reference.upper():
        return False
    if activator and str(item.get("activator", "")).upper() != activator.upper():
        return False
    return True


@mcp.tool()
def pota_scheduled(
    location: str | None = "",
    reference: str | None = "",
    activator: str | None = "",
    within_hours: float | None = None,
) -> dict[str, Any]:
    """Get upcoming scheduled POTA activations.

    All filters are optional and combine with AND — omit them all and the
    whole schedule comes back, as before.

    Args:
        location: Filter by location code (e.g., US-ID, CA-ON). Matches a park
            that spans regions, so US-MD finds a park listed as US-VA,US-MD.
            Empty for all.
        reference: Filter by park reference (e.g., US-0058). Empty for all.
        activator: Filter by activator callsign (e.g., N3VEM). Empty for all.
        within_hours: Only activations whose start time falls between now and
            this many hours from now. An activation already under way is not
            included — pota_spots is what reports the air now. Omit for no
            time limit.

    Returns:
        List of scheduled activations with activator, park, date, time window,
        planned frequencies, and comments. When a filter is given, the result
        also says what was asked for and how many activations were available
        before filtering.
    """
    try:
        # Coerce None → "" (llama.cpp/mcpo sends null for optional params, #1)
        location = location or ""
        reference = reference or ""
        activator = activator or ""
        items = _get_client().scheduled()
        available = len(items)

        matched = [i for i in items if _matches(i, location, reference, activator)]

        # The time window is applied after the text filters so the unreadable
        # count below is about the activations the operator actually asked for.
        unreadable = 0
        if within_hours is not None:
            # "Starts within the next N hours", exactly that: between now and
            # then. An activation already under way is not starting, and
            # pota_spots is the tool for what is on the air now. A grace period
            # either side would be this tool inventing a meaning the caller did
            # not ask for.
            #
            # Clamped because a float can be inf or nan: timedelta(hours=inf)
            # raises, and every comparison against nan is false, which would
            # empty the list for no stated reason.
            hours = float(within_hours)
            hours = 0.0 if hours != hours else min(max(hours, 0.0), 24.0 * 366)
            now = datetime.now(timezone.utc)
            until = now + timedelta(hours=hours)
            kept = []
            for item in matched:
                start = _starts_at(item)
                if start is None:
                    unreadable += 1
                    continue
                if now <= start <= until:
                    kept.append(item)
            matched = kept

        result: dict[str, Any] = {"total": len(matched), "activations": matched}
        asked = {
            k: v
            for k, v in (
                ("location", location.upper()),
                ("reference", reference.upper()),
                ("activator", activator.upper()),
                ("within_hours", within_hours),
            )
            if v not in ("", None)
        }
        if asked:
            # Only when something was asked for, so an unfiltered call returns
            # exactly the shape it always did.
            result["filters"] = asked
            result["available"] = available
            if unreadable:
                # Never silently dropped: an activation missing from the list
                # looks the same as one that was never scheduled.
                result["start_time_unreadable"] = unreadable
                result["start_time_unreadable_note"] = (
                    f"{unreadable} activation(s) matched the other filters but POTA did not give a "
                    "readable start date and time, so the time window could not be applied to them. "
                    "Omit within_hours to see them."
                )
        return result
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
    radius_km: float | None = 50.0,
    limit: int | None = 25,
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
        # Coerce None → defaults (llama.cpp/mcpo sends null for optional params)
        radius_km = radius_km if radius_km is not None else 50.0
        limit = limit if limit is not None else 25
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
