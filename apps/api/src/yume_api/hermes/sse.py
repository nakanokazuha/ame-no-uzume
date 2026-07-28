import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError

from yume_api.hermes.models import HermesStreamEvent

INVALID_SSE_EVENT_MESSAGE = "Hermes sent an invalid SSE event"
logger = logging.getLogger(__name__)


async def iter_sse(lines: AsyncIterator[str]) -> AsyncIterator[HermesStreamEvent]:
    """Decode JSON-valued SSE frames while ignoring comments and empty frames."""
    event_name = "message"
    data_lines: list[str] = []

    async for line in lines:
        if not line:
            event = _decode_event(event_name, data_lines)
            if event is not None:
                yield event
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].removeprefix(" "))

    event = _decode_event(event_name, data_lines)
    if event is not None:
        yield event


def _decode_event(event_name: str, data_lines: list[str]) -> HermesStreamEvent | None:
    if not data_lines:
        return None
    try:
        decoded: Any = json.loads("\n".join(data_lines))
        return HermesStreamEvent(event=event_name, data=decoded)
    except (json.JSONDecodeError, ValidationError):
        logger.warning(INVALID_SSE_EVENT_MESSAGE)
        return None
