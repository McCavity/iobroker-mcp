# iobroker-mcp

> Read/write access to an [ioBroker](https://www.iobroker.net/) installation via Model Context Protocol.

Wraps the ioBroker **SimpleAPI** adapter (`simple-api`, typical port 8087)
behind FastMCP tools. An LLM connected via MCP can then read sensor
states, flip switches, list objects with metadata, and (eventually) query
historical data — without speaking Socket.IO or JSON-RPC.

## Status

Early — skeleton with two tools. Read-side proves the API path works
against a real ioBroker (verified 2026-05-24 against an instance with
~25 active adapters and Tasmota / Twinkly / Zigbee devices). Write-side
+ bulk + history coming in the next iteration.

## Why SimpleAPI (and not REST API / admin / Socket.IO)?

- **SimpleAPI** is the lightest of the official adapters: simple URL
  scheme, ~10 endpoints, fast (sub-100ms for 275 KB object queries).
- Built for exactly this use-case (external scripted access).
- Supports optional Basic Auth.
- Trade-off: less polished metadata than the bigger `rest-api` (no
  Swagger UI), no OAuth2. For LAN-only Claude → ioBroker that's fine.

If you ever need Swagger or OAuth, the bigger `rest-api` adapter is a
drop-in alternative (different port, different envvar — minimal code
change here).

## Install

Requires Python 3.11+ (tested on 3.14, Homebrew). Requires the
SimpleAPI adapter installed and an active instance (`simple-api.0`) in
your ioBroker.

```bash
git clone git@github.com:McCavity/iobroker-mcp.git
cd iobroker-mcp

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set IOBROKER_URL (and user/pass if auth is on)
```

## Register as a Claude Code MCP

Add to `~/.claude.json` under `mcpServers` (user scope):

```json
"iobroker": {
  "type": "stdio",
  "command": "/Users/<you>/git/projects/own/iobroker-mcp/.venv/bin/python",
  "args": ["/Users/<you>/git/projects/own/iobroker-mcp/server.py"],
  "env": {}
}
```

Credentials come from `.env` next to `server.py`.

## Tool catalog

**Diagnostics**

| Tool | Description |
|---|---|
| `health_check` | Pings `/help` — confirms reachability, lists available SimpleAPI routes. |

**Read-side**

| Tool | Description |
|---|---|
| `read_state(state_id)` | Reads value + full metadata of a state. Handles Umlauts and spaces in state IDs. |

**Coming in the next iteration (phase C)**

- `write_state(state_id, value, ack?)` — set a state via `/set/<id>?value=…`
- `toggle_state(state_id)` — convenience toggle for boolean switches
- `read_states_bulk(state_ids)` — `/getBulk/<id1>,<id2>,…`
- `list_objects(pattern)` — `/objects?pattern=…` with Common-Metadata
- `search_objects(pattern)` — `/search?pattern=…`
- `query_history(state_id, from, to)` — `/query/…?dateFrom=…&dateTo=…`,
  pulls from the InfluxDB-backed history adapter

## Project layout

```
iobroker-mcp/
├── .env.example       # Template for IOBROKER_URL + optional auth
├── .gitignore         # Ignores .env, venv, caches
├── CLAUDE.md          # Conventions for AI agents working on this repo
├── LICENSE            # MIT
├── README.md          # This file
├── requirements.txt   # fastmcp, httpx, python-dotenv
└── server.py          # FastMCP server, all tools
```

## License

[MIT](LICENSE)
