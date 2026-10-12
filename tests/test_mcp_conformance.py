"""Conformance with the Model Context Protocol, revision 2026-07-28.

Nothing in this project's documents required this until 2026-10-11 — not
CLAUDE.md, not .claude/rules/security.md, not MCP-SECURITY-FRAMEWORK.md, not
qso-graph-spec. We documented how to *publish* an MCP server in detail and
never wrote down what makes one *valid*, which is how a missing ``isError`` and
missing annotations reached all 22 servers in the fleet unnoticed.

So these are asserted rather than trusted. ``get_version_info`` is the
cautionary case: a fleet convention nobody tested, which drifted.

Follows ``adif-mcp`` and ``solar-mcp``. What differs here is that this server's
refusals come in three kinds, and the distinction between them is the thing
easiest to get wrong — see ``TestWhatCountsAsAnError``.

Test IDs: POTA-C01 onward.
"""

from __future__ import annotations

import asyncio
import pathlib
import re

import pytest
from fastmcp.exceptions import ToolError

from pota_mcp import server

ANNOTATION_HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

# The ten that read api.pota.app, and the one that does not.
READS_POTA = {
    "pota_spots",
    "pota_park_info",
    "pota_park_stats",
    "pota_park_activations",
    "pota_park_leaderboard",
    "pota_user_stats",
    "pota_scheduled",
    "pota_location_parks",
    "pota_nearby_parks",
    "pota_rare_parks_near",
}
ANSWERS_FROM_THE_PACKAGE = {"get_version_info"}


def _tools() -> dict[str, object]:
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def _wire(tool: object) -> dict[str, object]:
    """The serialised annotations, which is what a client reads.

    Asserted on the wire form rather than the Python attributes: the SDK names
    its fields in snake_case and the protocol does not.
    """
    annotations = getattr(tool, "annotations", None)
    assert annotations is not None, "tool declares no annotations"
    return annotations.model_dump(by_alias=True, exclude_none=True)


def _call(name: str):
    """The underlying function of a registered tool."""
    tool = getattr(server, name)
    return getattr(tool, "fn", tool)


class TestToolAnnotations:
    def test_every_tool_declares_all_four_hints(self) -> None:
        """POTA-C01: the defaults are pessimistic, so silence is the wrong answer.

        Omitting them advertises a read-only tool as ``destructiveHint: true``
        and ``openWorldHint: true``, and the specification tells clients to keep
        a human in the loop for operations like that — so a client may
        reasonably put a confirmation prompt in front of looking up a park.
        """
        for name, tool in _tools().items():
            wire = _wire(tool)
            for hint in ANNOTATION_HINTS:
                assert hint in wire, f"{name} omits {hint} on the wire; got {sorted(wire)}"

    def test_every_tool_reads_and_none_writes(self) -> None:
        """POTA-C02: the three hints that describe effect.

        Every tool here fetches and reports. Nothing in this server writes
        anything, anywhere — ``pota_self_spot`` (#16) would be the first, and
        when it lands this test is where its hints must stop being the same as
        everyone else's.
        """
        for name, tool in _tools().items():
            wire = _wire(tool)
            assert wire["readOnlyHint"] is True, name
            assert wire["destructiveHint"] is False, name
            assert wire["idempotentHint"] is True, name

    def test_open_world_is_read_per_tool(self) -> None:
        """POTA-C03: the hint that is not the same for all of them.

        Ten tools reach POTA; ``get_version_info`` reports what the wheel
        carries and opens no connection. Setting them alike would make one of
        the two wrong, whichever value was chosen.
        """
        tools = _tools()
        assert set(tools) == READS_POTA | ANSWERS_FROM_THE_PACKAGE
        for name in READS_POTA:
            assert _wire(tools[name])["openWorldHint"] is True, name
        for name in ANSWERS_FROM_THE_PACKAGE:
            assert _wire(tools[name])["openWorldHint"] is False, name

    def test_the_server_really_does_reach_pota(self) -> None:
        """POTA-C04: the control for the ten ``openWorldHint: True``.

        A claim in an annotation is worth what the code behind it is worth.
        """
        src = pathlib.Path(server.__file__).parent
        outbound = re.compile(
            r"urllib\.request\.(urlopen|Request)|httpx\.|requests\.(get|post)"
        )
        reached = [p.name for p in src.rglob("*.py")
                   if outbound.search(p.read_text(encoding="utf-8", errors="replace"))]
        assert reached, "no outbound call found, so openWorldHint: True is not honest"


class TestToolErrorsAreFlagged:
    """A tool execution error belongs in the result with ``isError: true``.

    The specification states the cost of getting this wrong: otherwise "the LLM
    would not be able to see that an error occurred and self-correct". These
    returned ``{"error": "..."}`` as a *successful* result until #39, which a
    client cannot tell apart from an answer.
    """

    @pytest.fixture
    def broken(self, monkeypatch):
        """A client whose every call fails the way an unreachable API does."""
        class Broken:
            def __getattr__(self, _name):
                def fail(*_args, **_kwargs):
                    raise RuntimeError("POTA API request failed")
                return fail

        monkeypatch.setattr(server, "_get_client", lambda: Broken())

    @pytest.mark.parametrize("name,args", [
        ("pota_spots", ()),
        ("pota_park_info", ("US-0001",)),
        ("pota_park_stats", ("US-0001",)),
        ("pota_park_activations", ("US-0001",)),
        ("pota_park_leaderboard", ("US-0001",)),
        ("pota_user_stats", ("K4SWL",)),
        ("pota_scheduled", ()),
        ("pota_location_parks", ("US-ID",)),
    ])
    def test_an_upstream_failure_is_flagged(self, broken, name, args) -> None:
        """POTA-C10: every tool that can fail, not a sample of them.

        Parametrised because the old shape was applied by copy and paste: a
        single example would pass while nine others still returned a dict.
        """
        with pytest.raises(ToolError, match="POTA API request failed"):
            _call(name)(*args)

    def test_a_malformed_reference_is_flagged_without_a_request(self, monkeypatch) -> None:
        """POTA-C11: refused here rather than passed to POTA.

        POTA would answer 404, which says the park does not exist — a different
        fact from the reference being malformed, and the one a model can act on.
        """
        def never(*_args, **_kwargs):
            raise AssertionError("a request was sent for a malformed reference")

        monkeypatch.setattr(server, "_get_client", never)
        with pytest.raises(ToolError, match="not a park reference"):
            _call("pota_park_activations")("../../etc/passwd")

    def test_a_reference_with_no_park_is_flagged(self, monkeypatch) -> None:
        """POTA-C12: the refusal that was raised a layer down, in the client.

        A well-formed reference POTA holds nothing for used to come back as
        ``{"reference": ..., "error": "Not found"}`` — a successful result whose
        payload said it had failed.
        """
        from pota_mcp.client import POTAClient

        # Mock mode answers park_info from carried data and never calls
        # _get_json, so the patch below would not be reached with it on.
        monkeypatch.delenv("POTA_MCP_MOCK", raising=False)
        client = POTAClient()
        monkeypatch.setattr(client, "_get_json", lambda url: {})
        monkeypatch.setattr(client, "_cache_get", lambda key: None)
        monkeypatch.setattr(server, "_get_client", lambda: client)
        with pytest.raises(ToolError, match="no park US-9999"):
            _call("pota_park_info")("US-9999")


class TestWhatCountsAsAnError:
    """The distinction the specification draws, and the easy one to get wrong.

    Three things could each be called "nothing came back", and they are not the
    same:

    * a *malformed* reference — the caller can fix it (C11)
    * a well-formed reference POTA has no park for — the lookup cannot be
      answered at all (C12)
    * a *filter* matching nothing — the lookup succeeded and the answer is
      empty (C20)

    The first two are errors. The third is an answer, and reporting it as a
    failure would make a model retry a query that worked.
    """

    def test_no_spots_matching_a_filter_is_a_successful_call(self) -> None:
        """POTA-C20: "nobody is on RTTY right now" is an answer."""
        answer = _call("pota_spots")(mode="RTTY")
        assert isinstance(answer, dict)
        # "total", not "count": each individual spot carries a "count" of its
        # own (QSOs worked), which is a different number entirely.
        assert answer["total"] == 0
        assert answer["spots"] == []

    def test_a_normal_lookup_is_a_successful_call(self) -> None:
        """POTA-C21: the control — the above refuses some things, not everything."""
        answer = _call("pota_park_info")("US-0001")
        assert answer["reference"] == "US-0001"


class TestVersionInfoShape:
    def test_it_matches_the_shape_the_fleet_returns(self) -> None:
        """POTA-C30: the convention that drifted because nobody asserted it."""
        info = _call("get_version_info")()
        assert info["service_name"] == "pota-mcp"
        assert info["service_version"]
        assert info["spec_version"]


class TestRegistration:
    def test_the_eleven_tools_a_client_sees(self) -> None:
        """POTA-C40: calling a function directly is not proof a client can."""
        assert set(_tools()) == READS_POTA | ANSWERS_FROM_THE_PACKAGE
