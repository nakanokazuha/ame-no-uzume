import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, Self

import httpx
from pydantic import TypeAdapter

from yume_api.contracts.events import ConversationMessage
from yume_api.hermes.models import (
    HermesCapabilities,
    HermesCapabilitiesResponse,
    HermesContentPart,
    HermesRun,
    HermesRunCreated,
    HermesSessionCreated,
    HermesSessionMessage,
    HermesStreamEvent,
)
from yume_api.hermes.sse import iter_sse

POLL_INTERVAL_SECONDS = 1
EMPTY_API_KEY_MESSAGE = "Hermes API key must not be empty"
INCOMPATIBLE_CAPABILITIES_MESSAGE = "Hermes exposes neither session streaming nor compatible runs"
TERMINAL_RUN_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})
RUNS_SSE_FALLBACK_MESSAGE = "Runs SSE is unavailable; polling for terminal status"
_SESSION_MESSAGE_OBJECTS = TypeAdapter(list[dict[str, Any]])
_MESSAGE_CONTENT = TypeAdapter(str | list[HermesContentPart])
logger = logging.getLogger(__name__)


class HermesClient:
    """Authenticated, server-side client for the Hermes Gateway API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        if not api_key:
            raise ValueError(EMPTY_API_KEY_MESSAGE)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(30, read=None),
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned HTTP connection pool."""
        await self._client.aclose()

    async def get_capabilities(self) -> HermesCapabilities:
        """Discover the feature subset exposed by the connected Hermes instance."""
        response = await self._client.get("/v1/capabilities")
        response.raise_for_status()
        return HermesCapabilitiesResponse.model_validate(response.json()).features

    async def create_session(self, title: str) -> str:
        """Create a named persistent Hermes conversation and return its ID."""
        response = await self._client.post("/api/sessions", json={"title": title})
        response.raise_for_status()
        return HermesSessionCreated.model_validate(response.json()).id

    async def stream_session_chat(
        self, session_id: str, text: str
    ) -> AsyncIterator[HermesStreamEvent]:
        """Stream session chat events from the native session endpoint."""
        async with self._client.stream(
            "POST",
            f"/api/sessions/{session_id}/chat/stream",
            json={"input": text},
        ) as response:
            response.raise_for_status()
            async for event in iter_sse(response.aiter_lines()):
                yield event

    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        """Return user and assistant messages from a persistent Hermes session."""
        response = await self._client.get(f"/api/sessions/{session_id}/messages")
        response.raise_for_status()
        raw_messages = _SESSION_MESSAGE_OBJECTS.validate_python(response.json())
        messages: list[ConversationMessage] = []
        for item in raw_messages:
            if item.get("role") not in {"user", "assistant"}:
                continue
            message = HermesSessionMessage.model_validate(item)
            messages.append(
                ConversationMessage(
                    message_id=message.id,
                    role=message.role,
                    text=extract_text(message.content),
                )
            )
        return messages

    async def stream_task(
        self,
        capabilities: HermesCapabilities,
        session_id: str,
        text: str,
        history: list[ConversationMessage],
    ) -> AsyncIterator[HermesStreamEvent]:
        """Stream a task through session chat or the compatible Runs API."""
        if capabilities.session_chat_stream:
            async for event in self.stream_session_chat(session_id, text):
                yield event
            return
        if not capabilities.run_submission or not capabilities.run_status:
            raise RuntimeError(INCOMPATIBLE_CAPABILITIES_MESSAGE)
        run_id = await self.create_run(session_id, text, history)
        if capabilities.run_events_sse:
            try:
                async for event in self.stream_run_events(run_id):
                    yield event
                    if event.event in TERMINAL_RUN_EVENTS:
                        return
            except httpx.HTTPError:
                logger.warning(RUNS_SSE_FALLBACK_MESSAGE)
        async for event in self._poll_run_until_terminal(run_id):
            yield event

    async def _poll_run_until_terminal(self, run_id: str) -> AsyncIterator[HermesStreamEvent]:
        """Poll a run until it reaches a terminal status."""
        while True:
            run = await self.get_run(run_id)
            if run.status in {"completed", "failed", "cancelled"}:
                yield run_status_to_event(run)
                return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def create_run(
        self, session_id: str, text: str, history: list[ConversationMessage]
    ) -> str:
        """Create a compatible run using the dashboard session transcript."""
        response = await self._client.post(
            "/v1/runs",
            json={
                "input": text,
                "session_id": session_id,
                "conversation_history": [
                    {"role": item.role, "content": item.text} for item in history
                ],
            },
        )
        response.raise_for_status()
        return HermesRunCreated.model_validate(response.json()).run_id

    async def stream_run_events(self, run_id: str) -> AsyncIterator[HermesStreamEvent]:
        """Stream events for a compatible Hermes run."""
        async with self._client.stream("GET", f"/v1/runs/{run_id}/events") as response:
            response.raise_for_status()
            async for event in iter_sse(response.aiter_lines()):
                yield event

    async def get_run(self, run_id: str) -> HermesRun:
        """Fetch the current state of a compatible Hermes run."""
        response = await self._client.get(f"/v1/runs/{run_id}")
        response.raise_for_status()
        return HermesRun.model_validate(response.json())

    async def stop_run(self, run_id: str) -> None:
        """Request a capability-advertised compatible run stop."""
        response = await self._client.post(f"/v1/runs/{run_id}/stop")
        response.raise_for_status()

    async def resolve_approval(self, run_id: str, approval_id: str, *, approved: bool) -> None:
        """Resolve a capability-advertised pending compatible-run approval."""
        response = await self._client.post(
            f"/v1/runs/{run_id}/approval", json={"approval_id": approval_id, "approved": approved}
        )
        response.raise_for_status()


def extract_text(content: object) -> str:
    """Extract displayable text from a string or structured Hermes content."""
    normalized = _MESSAGE_CONTENT.validate_python(content)
    if isinstance(normalized, str):
        return normalized
    return "".join(part.text or "" for part in normalized if part.type in {"text", "output_text"})


def run_status_to_event(run: HermesRun) -> HermesStreamEvent:
    """Convert a terminal polling result into the stream event contract."""
    event_names = {
        "completed": "run.completed",
        "failed": "run.failed",
        "cancelled": "run.cancelled",
    }
    event_name = event_names[run.status]
    return HermesStreamEvent(
        event=event_name,
        data={"run_id": run.run_id, "output": run.output, "error": run.error},
    )
