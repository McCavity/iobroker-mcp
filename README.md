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
| `read_states_bulk(state_ids)` | Reads multiple states in one call via `/getBulk` — returns an array of `{id, val, ack, ts, …}`. |
| `list_objects(pattern, limit=50)` | Lists objects matching an ioBroker glob (`sonoff.*`, `zigbee.0.*`, `*.POWER`). Returns compact metadata (name, role, type, read/write). Limit caps the response size. |
| `search_objects(pattern)` | Faster ID-only search — returns flat list of state IDs, no metadata. Use when you only need names. |
| `query_history(state_id, date_from, date_to=now, aggregate="none", count=100)` | Pulls historical values via `/query` from whichever history adapter is configured in the SimpleAPI instance (set the "Datenquelle" dropdown to `influxdb.0` or similar). ISO 8601 timestamps. |

**Write-side**

| Tool | Description |
|---|---|
| `write_state(state_id, value, ack=False)` | Sets a state via `/set/<id>?value=…`. Booleans serialised as `true`/`false`. `ack=True` marks the write as device-confirmed (rare from MCP). |
| `toggle_state(state_id)` | Flips a boolean state via `/toggle` — convenience for switches. |

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
