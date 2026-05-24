"""iobroker-mcp — Read/write access to an ioBroker SimpleAPI via MCP.

Wraps the ioBroker SimpleAPI adapter (`simple-api`, typical port 8087)
behind FastMCP tools so an LLM can read sensor states, flip switches,
list objects with metadata, and (eventually) query historical data.

Transport: stdio. Registered as user-scope MCP in ~/.claude.json.

Skeleton state — phase B of the ioBroker-Erschließung plan
(see ~/.claude/plans/ich-w-rde-gerne-noch-immutable-token.md). Two
tools live: health_check + read_state. More tools (write_state,
list_objects, query_history) follow in phase C.

Sibling to paperless-bulk-mcp and nanobanana-render-mcp — same FastMCP
scaffolding pattern. Auth via optional basic auth (user/pass in .env)
matching the SimpleAPI adapter's "Authentifizierung" setting.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))

IOBROKER_URL = os.environ.get("IOBROKER_URL", "").rstrip("/")
IOBROKER_USER = os.environ.get("IOBROKER_USER", "")
IOBROKER_PASS = os.environ.get("IOBROKER_PASS", "")
IOBROKER_TIMEOUT = float(os.environ.get("IOBROKER_TIMEOUT", "10"))

if not IOBROKER_URL:
    print(
        "iobroker-mcp: IOBROKER_URL must be set "
        "(via .env next to server.py, or the host's env block).",
        file=sys.stderr,
    )
    sys.exit(1)


def _auth() -> tuple[str, str] | None:
    """Return (user, pass) tuple for httpx.auth if creds are configured,
    else None (LAN-open install)."""
    if IOBROKER_USER and IOBROKER_PASS:
        return (IOBROKER_USER, IOBROKER_PASS)
    return None


def _encode_id(state_id: str) -> str:
    """URL-encode an ioBroker state ID. Umlauts and spaces are common
    in human-named states (e.g. `sonoff.0.Büro.POWER`,
    `sonoff.0.Wohnzimmer Couch.POWER`)."""
    # safe='.' keeps dot separators readable in the URL
    return quote(state_id, safe=".")


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("iobroker")


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Smoke test: confirm we can reach the ioBroker SimpleAPI.

    Hits the `/help` endpoint which lists all supported routes. A
    healthy response means the adapter is up, the port is open, and
    auth (if any) works. Use this when something feels broken before
    digging into specific states.
    """
    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/help")
        resp.raise_for_status()
        endpoints = resp.json()

    return {
        "reachable": True,
        "url": IOBROKER_URL,
        "endpoints": sorted(endpoints.keys()) if isinstance(endpoints, dict) else [],
        "auth_configured": _auth() is not None,
    }


@mcp.tool()
def read_state(state_id: str) -> dict[str, Any]:
    """Read the current value + metadata of an ioBroker state.

    Returns the full state object: current value (`val`), acknowledge
    flag (`ack`), source (`from`), timestamp (`ts`), last-change
    (`lc`), plus the object's `common` block (name, role, type,
    read/write flags). Use this for sensor readings and switch states.

    Args:
        state_id: Dotted state ID, e.g. `sonoff.0.Büro.POWER` or
            `0_userdata.0.trigger.scenes.lighting.christmas`. Umlauts
            and spaces are handled by URL-encoding internally.
    """
    encoded = _encode_id(state_id)
    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/get/{encoded}")

    if resp.status_code == 404:
        return {"ok": False, "error": "state not found", "state_id": state_id}
    if resp.status_code >= 400:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
            "state_id": state_id,
        }

    return {"ok": True, "state_id": state_id, "state": resp.json()}


# ---------------------------------------------------------------------------
# Future tools (phase C of the plan)
# ---------------------------------------------------------------------------
# - write_state(state_id, value, ack?)  → /set/<id>?value=...
# - toggle_state(state_id)              → /toggle/<id>
# - read_states_bulk(state_ids)         → /getBulk/<id1>,<id2>,...
# - list_objects(pattern)               → /objects?pattern=...
# - search_objects(pattern)             → /search?pattern=...
# - query_history(state_id, from, to)   → /query/<id>?dateFrom=...&dateTo=...
#
# Add them once the read-side feels stable in real use.


if __name__ == "__main__":
    mcp.run()
