"""MCP server for Parks on the Air — park lookup, activator/hunter stats, spots"""

from __future__ import annotations

try:
    from importlib.metadata import version

    __version__ = version("pota-mcp")
except Exception:
    __version__ = "0.0.0-dev"
