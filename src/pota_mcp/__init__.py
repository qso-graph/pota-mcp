"""MCP server for Parks on the Air — park lookup, activator/hunter stats, spots"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Final

try:
    _pkg_version = version("pota-mcp")
except PackageNotFoundError:  # local dev / editable installs without dist metadata
    _pkg_version = "0.0.0-dev"

__version__: Final[str] = _pkg_version

# Upstream data spec the server is bound to. Pinned to the POTA public API
# version we consume — bump this when pota.app publishes a new API contract.
# Reported by the get_version_info tool so agents can detect fleet drift
# without going outside the MCP protocol.
__spec_version__: Final[str] = "pota-api-v1"
