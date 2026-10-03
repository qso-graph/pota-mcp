<!-- mcp-name: io.github.qso-graph/pota-mcp -->
# pota-mcp

[![PyPI](https://img.shields.io/pypi/v/pota-mcp?label=PyPI&color=blue)](https://pypi.org/project/pota-mcp/)
[![MCP Registry](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fregistry.modelcontextprotocol.io%2Fv0%2Fservers%3Fsearch%3Dio.github.qso-graph%2Fpota-mcp%26version%3Dlatest&query=%24.servers%5B0%5D.server.version&label=MCP%20Registry&color=blue)](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.qso-graph/pota-mcp&version=latest)

MCP server for [Parks on the Air (POTA)](https://pota.app/) — live activator spots, park info, activator/hunter stats, and scheduled activations through any MCP-compatible AI assistant.

Part of the [qso-graph](https://qso-graph.io/) project. **No authentication required** — all POTA endpoints are public.

## Install

```bash
uvx pota-mcp            # run it; nothing to install
```

## Tools

| Tool | Description |
|------|-------------|
| `pota_spots` | Current activator spots with park/grid enrichment and optional filters |
| `pota_park_info` | Park details by reference code (name, grid, type, agencies, website) |
| `pota_park_stats` | Activation and QSO counts for a park |
| `pota_user_stats` | Activator/hunter stats by callsign |
| `pota_scheduled` | Upcoming scheduled activations |
| `pota_location_parks` | All parks in a state/province/country |
| `pota_nearby_parks` | Find parks near a point — great for 2-fer planning |
| `get_version_info` | Service version + upstream spec version (fleet identity attestation) |

## Quick Start

No credentials needed — just install and configure your MCP client.

### Configure your MCP client

pota-mcp works with any MCP-compatible client. Add the server config and restart — tools appear automatically.

#### Claude Desktop

Add to `claude_desktop_config.json` (`~/Library/Application Support/Claude/` on macOS, `%APPDATA%\Claude\` on Windows):

```json
{
  "mcpServers": {
    "pota": {
      "command": "uvx",
      "args": ["pota-mcp"]
    }
  }
}
```

#### Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "pota": {
      "command": "uvx",
      "args": ["pota-mcp"]
    }
  }
}
```

#### ChatGPT Desktop

```json
{
  "mcpServers": {
    "pota": {
      "command": "uvx",
      "args": ["pota-mcp"]
    }
  }
}
```

#### Cursor

Add to `.cursor/mcp.json` (project-level) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "pota": {
      "command": "uvx",
      "args": ["pota-mcp"]
    }
  }
}
```

#### VS Code / GitHub Copilot

Add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "pota": {
      "command": "uvx",
      "args": ["pota-mcp"]
    }
  }
}
```

#### Gemini CLI

Add to `~/.gemini/settings.json` (global) or `.gemini/settings.json` (project):

```json
{
  "mcpServers": {
    "pota": {
      "command": "uvx",
      "args": ["pota-mcp"]
    }
  }
}
```

### Ask questions

> "What POTA activations are happening right now?"

> "Tell me about park US-0001 — how many activations has it had?"

> "What are K4SWL's POTA stats?"

> "Show me all parks in Idaho"

> "Are there any CW activators on 20m right now?"

> "What activations are scheduled for tomorrow?"

## Testing Without Network

For testing all tools without hitting the POTA API:

```bash
POTA_MCP_MOCK=1 pota-mcp
```

## MCP Inspector

```bash
pota-mcp --transport streamable-http --port 8006
```

Then open the MCP Inspector at `http://localhost:8006`.

## Development

```bash
git clone https://github.com/qso-graph/pota-mcp.git
cd pota-mcp
uv sync --group dev
uv run pytest
```

## License

GPL-3.0-or-later
