# pota-mcp

MCP server for [Parks on the Air (POTA)](https://pota.app/) — live activator spots, park info, activator/hunter stats, and scheduled activations through any MCP-compatible AI assistant.

Part of the [qso-graph](https://qso-graph.io/) project. **No authentication required** — all POTA endpoints are public.

## Install

```bash
pip install pota-mcp
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
      "command": "pota-mcp"
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
      "command": "pota-mcp"
    }
  }
}
```

#### ChatGPT Desktop

```json
{
  "mcpServers": {
    "pota": {
      "command": "pota-mcp"
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
      "command": "pota-mcp"
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
      "command": "pota-mcp"
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
      "command": "pota-mcp"
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
pip install -e .
```

## License

GPL-3.0-or-later
