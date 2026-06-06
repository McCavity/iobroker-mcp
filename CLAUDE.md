# iobroker-mcp — Conventions for AI agents

> Last update: 2026-05-24

This file orients AI coding agents (Claude Code, Codex, etc.) when working
on this repository. Humans should read [README.md](README.md) first.

## What this project is

A Model Context Protocol server wrapping the ioBroker SimpleAPI adapter.
Sibling to `paperless-bulk-mcp` and `nanobanana-render-mcp` — same FastMCP
scaffolding, different domain.

Transport: stdio. Framework: [FastMCP](https://github.com/jlowin/fastmcp).

## Key design choices

- **Single `server.py`, no package split.** Two tools today, ~7 planned —
  expect to land at ~250 lines total. Split only if it grows past ~300.
- **SimpleAPI over REST API / Socket.IO / Admin JSON-RPC.** Cheapest path
  to a working tool with the smallest surface to maintain. Trade-offs
  documented in README.
- **`.env` next to `server.py`, not in CWD.** The MCP host launches us
  from arbitrary directories; we load `.env` relative to the file path.
- **Optional basic auth.** SimpleAPI defaults to no auth (typical
  LAN-install). If `IOBROKER_USER` and `IOBROKER_PASS` are set in env,
  we pass them as httpx basic-auth. If empty: no auth header sent.
- **URL-encoding of state IDs is mandatory.** ioBroker state names
  frequently contain Umlauts (`Büro`, `Eßzimmer`) and spaces
  (`Wohnzimmer Couch`). The `_encode_id` helper handles this — never
  build URLs with raw state IDs.

## ioBroker SimpleAPI quirks

- **Pattern matching is whole-string glob, not substring.** `/search`
  and `/objects` match the `pattern` parameter as a complete glob
  against the full state ID. A bare string like `smartcontrol` only
  matches the literal `smartcontrol` (which never exists — every
  real state is namespaced). We handle this in `_normalize_pattern`
  by appending `.*` to wildcard-free patterns. In-string substring
  wildcards like `*battery*` also don't work — those return zero, and
  so does a wildcard glued to a segment name without a separating dot
  (`zigbee.0.*battery`). The `*` must sit at a `.` boundary: use
  `zigbee.0.*.battery` or `*.battery`. Verified live 2026-06-06
  (`zigbee.0.*battery` → 0, `zigbee.0.*.battery` → 13). *(Possible
  future `_normalize_pattern` enhancement: when a pattern yields zero
  and has a `*` glued to a trailing segment, return a `hint`
  suggesting the dot-separated form — not implemented.)*
- **`/objects` filters `script.js.*`** — script objects don't show
  up in listings, likely for payload-size reasons. Use `read_state`
  with the exact script path to fetch sources. `list_objects` returns
  a `hint` field when a script.js pattern yields zero matches.
- **`/help` returns a JSON map** of endpoint name → example URL, not
  human-readable text. Useful as a smoke test.
- **`/get/<id>`** returns the full state object with `common`, `native`,
  `acl`, `val`, `ack`, `ts`, `lc`, `from`. Rich metadata is one of the
  reasons we chose SimpleAPI.
- **`/getPlainValue/<id>`** returns ONLY the value as a string — useful
  for shell scripts, less so for MCP (we want the metadata).
- **Bulk endpoints** (`/getBulk`, `/setBulk`) take comma-separated IDs.
  Watch out: URL length limits in some reverse proxies may cap this.
- **`/objects?pattern=`** can return very large payloads (we saw 275 KB
  for `sonoff.*` against ~25 active Tasmota devices). For large
  patterns consider streaming or chunked fetching.
- **`/query/<id>?dateFrom=…&dateTo=…`** pulls from whichever history
  adapter is configured (Henning uses InfluxDB). Returns time-series.
- **State IDs with dots are tricky.** ioBroker's namespace is
  dot-separated (`sonoff.0.Büro.POWER`), but the device name itself
  rarely contains dots, so safe-list `.` in URL-encoding is fine.

## Coding conventions

- Python 3.11+ (developed on Homebrew Python 3.14).
- Type hints everywhere (`from __future__ import annotations` at top).
- `httpx.Client` per call, no global client.
- Tool docstrings are the user-facing contract — write them as if the
  next user is an LLM that has nothing else to go on.
- Surface ioBroker errors verbatim (truncated to 500 chars). Don't
  invent error messages.

## Testing

TBD. For now: direct import + call from the Python REPL while running
against a real ioBroker. Pytest matrix when the tool count justifies it.

## Pattern hints for the future MCP template

This is the **third** MCP server using the same scaffolding (after
`paperless-bulk-mcp` and `nanobanana-render-mcp`). The pattern is now
clearly established — three data points:

What's identical across all three:

- `.env` loaded relative to `server.py`
- Fail-fast on missing env vars with stderr message + `sys.exit(1)`
- `_headers()` / `_auth()` helper closing over the auth config
- FastMCP boilerplate + `if __name__ == "__main__": mcp.run()`
- Single server.py, no package split

What's different:

- Auth header style (Token vs API key vs basic auth)
- Response shape (JSON dicts vs binary base64 vs JSON with deeply nested data)
- URL encoding needs (paperless: clean IDs / nanobanana: clean URLs /
  iobroker: Umlauts everywhere)

**Trigger for template extraction**: now reached (3 MCPs). See KI-OS
open loop "MCP-Server-Template extrahieren". Concrete next step would
be a `mcp-server-template` GitHub repo with "Use this template" flag.
