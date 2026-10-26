"""pota-mcp: MCP server for Parks on the Air — all public, no auth required."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import __spec_version__, __version__
from .client import POTAClient, regions, valid_reference

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

# MCP 2026-07-28 tool annotations. The defaults are pessimistic — a tool that
# declares nothing is advertised as destructive, non-idempotent and open-world,
# and the specification tells a client to keep a human in the loop for an
# operation like that. So a client would be entitled to put a confirmation
# prompt in front of looking up a park. Every tool here reads and none writes,
# so the three effect hints are the same for all of them; only openWorldHint
# differs, and it is read per tool.
#
# They are a client's UX hint and never a security control: the specification
# requires clients to treat them as untrusted, so none of this replaces the
# reference and callsign validation below.
_READS_POTA = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    # Reaches api.pota.app, which is outside this host.
    "openWorldHint": True,
}
_ANSWERS_FROM_THE_PACKAGE = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    # Reports versions carried in the wheel. It opens no connection.
    "openWorldHint": False,
}


def _park_reference(reference: str) -> str:
    """POTA's own reference format, checked before anything is sent.

    Said rather than passed on: POTA would answer 404 and the caller would be
    told the park does not exist, which is a different fact from the reference
    being malformed.

    Raised outside each tool's ``try`` so the generic handler there cannot
    re-wrap it. The message would survive that — a ToolError's ``str`` is its
    message — but relying on the coincidence would be worse than not nesting.
    """
    ref = reference.strip().upper()
    if not valid_reference(ref):
        raise ToolError(f"{reference!r} is not a park reference. They look like US-0062.")
    return ref



def _version_info_payload() -> dict[str, Any]:
    """Build the version info envelope. Pulled into a helper so tests can
    call it directly without going through the FastMCP wrapper."""
    return {
        "service_name": "pota-mcp",
        "service_version": __version__,
        "spec_version": __spec_version__,
    }


@mcp.tool(annotations=_ANSWERS_FROM_THE_PACKAGE)
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


@mcp.tool(annotations=_READS_POTA)
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
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
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
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
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
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
def pota_park_activations(reference: str, count: int | None = 10) -> dict[str, Any]:
    """List recent activations of a POTA park, most recent first.

    Answers "when was this park last activated?" and "is it often on the air?".

    Args:
        reference: Park reference code (e.g., US-0062).
        count: How many recent activations to return (default 10, max 50).

    Returns:
        Each activation's callsign, date, total QSOs and the CW, data and phone
        counts, with the park reference and how many were returned.
    """
    ref = _park_reference(reference)
    try:
        # Coerce None → default (llama.cpp/mcpo sends null for optional params, #1)
        count = count if count is not None else 10
        count = min(max(int(count), 1), 50)
        activations = _get_client().park_activations(ref, count=count)
        return {"reference": ref, "count": len(activations), "activations": activations}
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
def pota_park_leaderboard(reference: str, limit: int | None = 10) -> dict[str, Any]:
    """Top activators and hunters of a POTA park.

    Three boards: most activations, most QSOs as an activator, most QSOs as a
    hunter. Each row is a callsign and a count and nothing else.

    Args:
        reference: Park reference code (e.g., US-0062).
        limit: Rows per board (default 10, max 25). POTA currently publishes
            five per board, so a higher limit changes nothing until it does.

    Returns:
        The park reference and the three boards.
    """
    ref = _park_reference(reference)
    try:
        # Coerce None → default (llama.cpp/mcpo sends null for optional params, #1)
        limit = limit if limit is not None else 10
        limit = min(max(int(limit), 1), 25)
        boards = _get_client().park_leaderboard(ref, limit=limit)
        return {"reference": ref, **boards}
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
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
        raise ToolError(str(e)) from e


# ---------------------------------------------------------------------------
# Scheduled-activation filters (#20)
# ---------------------------------------------------------------------------
#
# Applied here rather than in the client, deliberately. `client.scheduled()`
# caches the whole feed under one key, so one cached fetch serves every
# combination of filters. `spots` takes the other route and keys its cache by
# its filters, which means a different band is a different cache entry and a
# fresh fetch.
#
# `regions` is the client's, shared with `spots` (#27): the region test was
# written here first and then found missing there, which is exactly what two
# copies of one rule does.


def _clock_time(value: object) -> tuple[int, int] | None:
    """`HH:MM` as POTA sends it, or `HHMM`, as (hour, minute). None if neither."""
    text = str(value or "").strip()
    digits = text.replace(":", "")
    if len(digits) not in (3, 4) or not digits.isdigit():
        return None
    hour, minute = int(digits[:-2]), int(digits[-2:])
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _utc_date(value: object) -> datetime | None:
    """A POTA `YYYY-MM-DD` as midnight UTC, or None."""
    try:
        day = datetime.strptime(str(value or "").strip(), "%Y-%m-%d")
        return day.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _starts_at(item: dict[str, Any], now: datetime | None = None) -> datetime | None:
    """The next time this activation starts, in UTC, or None if POTA did not say.

    A POTA schedule entry is a **date range plus a daily UTC window**:
    `startDate` and `endDate` are `YYYY-MM-DD`, `startTime` and `endTime` are
    `HH:MM`. A one-day activation has `startDate == endDate`; a standing one
    runs to a later `endDate` at the same `startTime` each day. So "starts" is
    the next occurrence of `startTime` on a day inside the range — and for an
    entry whose range has already passed, the last occurrence, which no future
    window contains.

    An entry whose start cannot be read is not silently dropped: the count of
    those is reported, because an activation missing from a filtered list looks
    the same as one that was never scheduled.

    Found by the live fixture check (#32). This read `activityDate`, which POTA
    does not send, and required `startTime` to be four digits, which `14:00` is
    not — so against the real API it returned None for every entry and the
    `within_hours` filter reported the whole schedule as unreadable.
    """
    clock = _clock_time(item.get("startTime"))
    begins = _utc_date(item.get("startDate"))
    if clock is None or begins is None:
        return None
    hour, minute = clock
    window = timedelta(hours=hour, minutes=minute)
    # endDate missing or unreadable: treat it as a single day, which is the
    # narrower reading and never invents a window POTA did not publish.
    ends = _utc_date(item.get("endDate")) or begins
    if ends < begins:
        ends = begins

    moment = now or datetime.now(timezone.utc)
    first = begins + window
    if moment <= first:
        return first
    # Inside the range, or past it: the next daily occurrence at or after now,
    # bounded by the last day the entry runs.
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if moment > day + window:
        day += timedelta(days=1)
    if day > ends:
        return ends + window
    return day + window


def _matches(
    item: dict[str, Any],
    location: str,
    reference: str,
    activator: str,
) -> bool:
    """Whether one activation passes every text filter given (AND)."""
    if location and location.upper() not in regions(item):
        return False
    if reference and str(item.get("reference", "")).upper() != reference.upper():
        return False
    if activator and str(item.get("activator", "")).upper() != activator.upper():
        return False
    return True


@mcp.tool(annotations=_READS_POTA)
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
                    f"{unreadable} activation(s) matched the other filters but POTA "
                    "did not give a readable start date and time, so the time window "
                    "could not be applied to them. Omit within_hours to see them."
                )
        return result
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
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
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
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
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READS_POTA)
def pota_rare_parks_near(
    location: str,
    latitude: float,
    longitude: float,
    radius_km: float | None = 50.0,
    limit: int | None = 25,
) -> dict[str, Any]:
    """Find the least-activated POTA parks near a point.

    Answers "which parks near me have never, or rarely, been activated?" —
    for an activator looking for something unworked, or a hunter looking for a
    rare one. Least activated first, nearest first among equals.

    Args:
        location: Location code (e.g., US-ID, CA-ON). Required to scope the search.
        latitude: Center point latitude (e.g., 43.617).
        longitude: Center point longitude (e.g., -115.993).
        radius_km: Search radius in km (default 50, max 500).
        limit: Maximum parks to return (default 25, max 100).

    Returns:
        Parks sorted by fewest activations then distance, each with
        distance_km, never_activated, and POTA's own activations, attempts and
        qsos counts. A park with attempts but no activations has been tried
        and not finished.
    """
    try:
        # Coerce None → defaults (llama.cpp/mcpo sends null for optional params, #1)
        radius_km = radius_km if radius_km is not None else 50.0
        limit = limit if limit is not None else 25
        radius_km = min(max(float(radius_km), 1.0), 500.0)
        limit = min(max(int(limit), 1), 100)
        parks = _get_client().rare_parks_near(
            location=location,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            limit=limit,
        )
        never = sum(1 for p in parks if p.get("never_activated"))
        return {
            "location": location.upper(),
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "total": len(parks),
            "never_activated": never,
            "parks": parks,
        }
    except Exception as e:
        raise ToolError(str(e)) from e


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


USAGE = """\
usage: pota-mcp [--transport stdio|streamable-http] [--port N] [--version] [--help]

An MCP server: an AI app (Claude Desktop, Claude Code, ...) starts it and talks
to it over stdio. Run on its own it waits for that app; press Ctrl-C to stop.
Set up a client: https://github.com/qso-graph/pota-mcp#quick-start

streamable-http binds 127.0.0.1 only: not another machine,
not a container.
"""


def main() -> None:
    """Run the pota-mcp server."""
    # Without this the script ignored both flags and bound stdio, so
    # `--help` left a user watching a banner and a hung terminal.
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(USAGE, end="")
        return
    if "--version" in sys.argv[1:]:
        print(f"pota-mcp {__version__}")
        return
    transport = "stdio"
    port = 8006
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--transport" and i < len(sys.argv) - 1:
            transport = sys.argv[i + 1]
        if arg == "--port" and i < len(sys.argv) - 1:
            port = int(sys.argv[i + 1])

    # Written out rather than passed through: fastmcp takes a literal, and a
    # str that happens to hold the right word is not the same thing.
    if transport == "streamable-http":
        # Where it bound, said out loud. FastMCP binds 127.0.0.1 and takes
        # no host option, so this is never reachable from another machine
        # or from outside a container. Silent before this line.
        print(
            f"pota-mcp on http://127.0.0.1:{port}/mcp - loopback only",
            file=sys.stderr,
        )
        mcp.run(transport="streamable-http", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
