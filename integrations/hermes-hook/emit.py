#!/usr/bin/env python3
"""Emit bounded Hermes lifecycle telemetry to a local Yume dashboard."""

import json
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOOK_TIMEOUT_SECONDS = 1
ALLOWED = {
    "subagent_start": {"child_subagent_id", "child_role", "child_goal"},
    "subagent_stop": {
        "child_subagent_id",
        "child_role",
        "child_status",
        "duration_ms",
        "tool_call_history",
    },
}


def _reduce_tool_history(history: object) -> list[dict[str, object]]:
    """Keep only the approved name and status from each tool invocation."""
    if not isinstance(history, Sequence) or isinstance(history, str | bytes):
        return []
    return [
        {
            "tool_name": item.get("tool_name"),
            "status": item.get("status"),
        }
        for item in history
        if isinstance(item, Mapping)
    ]


def _approved_extra(event: str, payload: Mapping[str, object]) -> dict[str, object]:
    """Return the event-specific allow-list without copying source payloads."""
    permitted = ALLOWED.get(event)
    raw_extra = payload.get("extra")
    if permitted is None or not isinstance(raw_extra, Mapping):
        return {}
    extra = {
        key: value
        for key, value in raw_extra.items()
        if isinstance(key, str) and key in permitted
    }
    if "tool_call_history" in extra:
        extra["tool_call_history"] = _reduce_tool_history(extra["tool_call_history"])
    return extra


def emit(event: str, payload: dict[str, object]) -> dict[str, object]:
    """Best-effort post one privacy-bounded lifecycle event and return hook JSON."""
    if event not in ALLOWED:
        return {}

    envelope = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "event": event,
        "session_id": payload.get("session_id", ""),
        "extra": _approved_extra(event, payload),
    }
    try:
        request = Request(
            os.environ["YUME_HOOK_URL"],
            data=json.dumps(envelope).encode(),
            headers={
                "Authorization": f"Bearer {os.environ['YUME_HOOK_TOKEN']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urlopen(request, timeout=HOOK_TIMEOUT_SECONDS).read()
    except (HTTPError, KeyError, TimeoutError, URLError, ValueError):
        pass
    return {}


def main(arguments: Sequence[str]) -> dict[str, object]:
    """Read a Hermes hook payload while leaving malformed hook input non-blocking."""
    try:
        event = arguments[1]
        payload = json.load(sys.stdin)
    except (IndexError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return emit(event, payload)


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
