#!/usr/bin/env python3
"""Emit bounded Hermes lifecycle telemetry to a local Yume dashboard."""

import json
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from urllib.request import Request, urlopen

HOOK_TIMEOUT_SECONDS = 1
MAX_SESSION_ID_LENGTH = 256
MAX_CHILD_SESSION_ID_LENGTH = 256
MAX_CHILD_SUBAGENT_ID_LENGTH = 256
MAX_CHILD_ROLE_LENGTH = 64
MAX_CHILD_GOAL_LENGTH = 1_000
MAX_CHILD_STATUS_LENGTH = 64
MAX_DURATION_MS = 604_800_000
MAX_TOOL_HISTORY_LENGTH = 100
MAX_TOOL_NAME_LENGTH = 128
MAX_TOOL_STATUS_LENGTH = 64
TEXT_FIELDS = {
    "subagent_start": {
        "child_session_id": MAX_CHILD_SESSION_ID_LENGTH,
        "child_subagent_id": MAX_CHILD_SUBAGENT_ID_LENGTH,
        "child_role": MAX_CHILD_ROLE_LENGTH,
        "child_goal": MAX_CHILD_GOAL_LENGTH,
    },
    "subagent_stop": {
        "child_session_id": MAX_CHILD_SESSION_ID_LENGTH,
        "child_subagent_id": MAX_CHILD_SUBAGENT_ID_LENGTH,
        "child_role": MAX_CHILD_ROLE_LENGTH,
        "child_status": MAX_CHILD_STATUS_LENGTH,
    },
}


def _bounded_text(value: object, maximum_length: int) -> str | None:
    """Return a non-empty approved text value, never a nested JSON value."""
    if not isinstance(value, str) or not value or len(value) > maximum_length:
        return None
    return value


def _reduce_tool_history(history: object) -> list[dict[str, str]]:
    """Keep only the approved name and status from each tool invocation."""
    if not isinstance(history, list) or len(history) > MAX_TOOL_HISTORY_LENGTH:
        return []
    reduced: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        tool_name = _bounded_text(item.get("tool_name"), MAX_TOOL_NAME_LENGTH)
        status = _bounded_text(item.get("status"), MAX_TOOL_STATUS_LENGTH)
        if tool_name is not None and status is not None:
            reduced.append({"tool_name": tool_name, "status": status})
    return reduced


def _approved_extra(event: str, payload: Mapping[str, object]) -> dict[str, object]:
    """Return the event-specific allow-list without copying source payloads."""
    permitted = TEXT_FIELDS.get(event)
    raw_extra = payload.get("extra")
    if permitted is None or not isinstance(raw_extra, Mapping):
        return {}
    extra: dict[str, object] = {}
    for key, maximum_length in permitted.items():
        value = _bounded_text(raw_extra.get(key), maximum_length)
        if value is not None:
            extra[key] = value
    if event == "subagent_stop":
        duration = raw_extra.get("duration_ms")
        if type(duration) is int and 0 <= duration <= MAX_DURATION_MS:
            extra["duration_ms"] = duration
        history = _reduce_tool_history(raw_extra.get("tool_call_history"))
        if history:
            extra["tool_call_history"] = history
    return extra


def emit(event: str, payload: dict[str, object]) -> dict[str, object]:
    """Best-effort post one privacy-bounded lifecycle event and return hook JSON."""
    try:
        if event not in TEXT_FIELDS:
            return {}
        session_id = (
            _bounded_text(payload.get("session_id"), MAX_SESSION_ID_LENGTH) or ""
        )
        envelope = {
            "schema_version": 1,
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(UTC).isoformat(),
            "event": event,
            "session_id": session_id,
            "extra": _approved_extra(event, payload),
        }
        request = Request(
            os.environ["YUME_HOOK_URL"],
            data=json.dumps(envelope).encode(),
            headers={
                "Authorization": f"Bearer {os.environ['YUME_HOOK_TOKEN']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response = urlopen(request, timeout=HOOK_TIMEOUT_SECONDS)
        response.close()
    except Exception:  # noqa: BLE001 - shell hooks must never interrupt Hermes.
        return {}
    return {}


def main(arguments: Sequence[str]) -> dict[str, object]:
    """Read a Hermes hook payload while leaving malformed hook input non-blocking."""
    try:
        event = arguments[1]
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return {}
        return emit(event, payload)
    except Exception:  # noqa: BLE001 - hook input failures must not block Hermes.
        return {}


if __name__ == "__main__":
    try:
        print(json.dumps(main(sys.argv)))
    except Exception:  # noqa: BLE001 - preserve the required hook response.
        print("{}")
