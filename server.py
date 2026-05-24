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
from datetime import datetime, timezone
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


# --- Write side -----------------------------------------------------------


@mcp.tool()
def write_state(
    state_id: str,
    value: bool | int | float | str,
    ack: bool = False,
) -> dict[str, Any]:
    """Write a value to a state via the SimpleAPI `/set` endpoint.

    The SimpleAPI uses GET (not POST) with the value in the query
    string — a quirk of the adapter. We handle that internally.

    Args:
        state_id: Target state, e.g. `sonoff.0.Büro.POWER`.
        value: New value. Bools are serialised to `true`/`false`,
            numbers and strings get `str(value)`.
        ack: If True, mark the write as acknowledged (i.e. coming
            from the device itself, not a command). Default False
            (the value is a command). Most LLM-driven writes should
            keep this False so adapters can react properly.
    """
    encoded = _encode_id(state_id)
    if isinstance(value, bool):
        v_str = "true" if value else "false"
    else:
        v_str = str(value)

    params: dict[str, str] = {"value": v_str}
    if ack:
        params["ack"] = "true"

    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/set/{encoded}", params=params)

    if resp.status_code >= 400:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
            "state_id": state_id,
        }

    try:
        body = resp.json() if resp.text else None
    except ValueError:
        body = resp.text[:200]

    return {
        "ok": True,
        "state_id": state_id,
        "value_sent": value,
        "ack": ack,
        "response": body,
    }


@mcp.tool()
def toggle_state(state_id: str) -> dict[str, Any]:
    """Toggle a boolean state via `/toggle`.

    Convenience for switches: reads the current value, inverts it,
    writes back. Only works for boolean states (returns an error
    from ioBroker otherwise). Use `write_state` for non-bool writes.
    """
    encoded = _encode_id(state_id)
    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/toggle/{encoded}")

    if resp.status_code >= 400:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
            "state_id": state_id,
        }

    return {"ok": True, "state_id": state_id, "response": resp.json()}


# --- Bulk + lookup --------------------------------------------------------


@mcp.tool()
def read_states_bulk(state_ids: list[str]) -> dict[str, Any]:
    """Read multiple states in one request via `/getBulk`.

    Useful for dashboards or correlated reads (e.g. all Tasmota power
    readings at once). Each state ID is URL-encoded; commas are added
    automatically.

    Args:
        state_ids: List of dotted state IDs.
    """
    if not state_ids:
        return {"ok": False, "error": "state_ids must not be empty"}

    encoded_list = ",".join(_encode_id(sid) for sid in state_ids)
    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/getBulk/{encoded_list}")

    if resp.status_code >= 400:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
        }

    return {
        "ok": True,
        "count_requested": len(state_ids),
        "states": resp.json(),
    }


@mcp.tool()
def list_objects(pattern: str, limit: int = 50) -> dict[str, Any]:
    """List objects matching an ioBroker wildcard pattern via `/objects`.

    Pattern uses ioBroker glob style: `sonoff.*`, `zigbee.0.*`,
    `0_userdata.0.trigger.*`. Beware large result sets — `/objects` can
    return hundreds of KB for broad patterns. The `limit` argument caps
    the returned list (sorted by state ID) to keep MCP responses small.

    Returns compact metadata per object: id, name, role, type, read /
    write flags. Use `read_state` afterwards if you need the full
    object including custom blocks and ACL.
    """
    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/objects", params={"pattern": pattern})

    if resp.status_code >= 400:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
            "pattern": pattern,
        }

    full = resp.json() if isinstance(resp.json(), dict) else {}
    keys = sorted(full.keys())
    truncated = len(keys) > limit
    selected = keys[:limit]

    compact = []
    for k in selected:
        obj = full.get(k, {}) or {}
        common = obj.get("common", {}) or {}
        compact.append({
            "id": k,
            "name": common.get("name", ""),
            "role": common.get("role", ""),
            "type": common.get("type", ""),
            "read": common.get("read", True),
            "write": common.get("write", False),
        })

    return {
        "ok": True,
        "pattern": pattern,
        "total_matches": len(keys),
        "returned": len(selected),
        "truncated": truncated,
        "objects": compact,
    }


@mcp.tool()
def search_objects(pattern: str) -> dict[str, Any]:
    """Search for state IDs matching a pattern via `/search`.

    Faster than `list_objects` when you only need IDs (no metadata).
    Returns a flat list of state IDs.
    """
    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/search", params={"pattern": pattern})

    if resp.status_code >= 400:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
            "pattern": pattern,
        }

    body = resp.json()
    ids = body if isinstance(body, list) else list(body.keys() if isinstance(body, dict) else [])
    return {"ok": True, "pattern": pattern, "count": len(ids), "ids": ids}


# --- History --------------------------------------------------------------


@mcp.tool()
def query_history(
    state_id: str,
    date_from: str,
    date_to: str | None = None,
    aggregate: str = "none",
    count: int = 100,
) -> dict[str, Any]:
    """Query historical values from the configured history adapter.

    Requires the state to have history enabled (Henning's setup writes
    to `influxdb.0` for most Tasmota / sensor states). The history adapter
    is queried via SimpleAPI's `/query` endpoint.

    Args:
        state_id: Target state ID.
        date_from: ISO 8601 timestamp, e.g. `2026-05-24T16:00:00.000Z`.
            Use UTC ("Z" suffix) for unambiguous results.
        date_to: ISO 8601 timestamp. Defaults to "now" (UTC) if omitted.
        aggregate: One of `none`, `minmax`, `average`, `min`, `max`,
            `total`, `count`. Use `minmax` for sparkline-style overviews,
            `none` for raw data points.
        count: Maximum data points to return. SimpleAPI defaults to 2000
            without `aggregate` — we cap at 100 to keep MCP responses sane.
    """
    if date_to is None:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    encoded = _encode_id(state_id)
    params = {
        "dateFrom": date_from,
        "dateTo": date_to,
        "aggregate": aggregate,
        "count": str(count),
    }

    with httpx.Client(timeout=IOBROKER_TIMEOUT, auth=_auth()) as client:
        resp = client.get(f"{IOBROKER_URL}/query/{encoded}", params=params)

    if resp.status_code >= 400:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
            "state_id": state_id,
        }

    body = resp.json()
    # SimpleAPI returns either an array directly or an envelope with data.
    points = body if isinstance(body, list) else body.get("data", body)
    return {
        "ok": True,
        "state_id": state_id,
        "date_from": date_from,
        "date_to": date_to,
        "aggregate": aggregate,
        "result": points,
    }


if __name__ == "__main__":
    mcp.run()
