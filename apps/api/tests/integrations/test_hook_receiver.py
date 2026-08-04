"""Integration tests for authenticated Hermes hook ingestion."""

from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

from yume_api.hermes.models import HermesCapabilities
from yume_api.main import AppRuntime, create_app

SAMPLE_EXTRA = {
    "child_subagent_id": "child-7",
    "child_role": "researcher",
    "child_goal": "Compare Hermes event hooks",
}
SAMPLE_START_ENVELOPE = {
    "schema_version": 1,
    "event_id": "hook-1",
    "occurred_at": "2026-07-27T00:00:00Z",
    "event": "subagent_start",
    "session_id": "parent-1",
    "extra": SAMPLE_EXTRA,
}


class HookRuntime:
    """Minimal runtime with a hook-token configuration for route-level tests."""

    def __init__(self, hook_token: SecretStr | None) -> None:
        self.hermes = object()
        self.world = AsyncMock()
        self.capabilities = HermesCapabilities()
        self.asset_pack = object()
        self.hook_token = hook_token
        self.close_hermes = False


@pytest_asyncio.fixture
async def client_and_world() -> AsyncIterator[tuple[httpx.AsyncClient, AsyncMock]]:
    runtime = HookRuntime(SecretStr("hook-secret"))
    app = create_app(runtime=cast("AppRuntime", runtime))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, runtime.world


@pytest.mark.asyncio
async def test_hook_rejects_wrong_token(
    client_and_world: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """Reject a bearer token that does not match the configured secret."""
    client, _ = client_and_world

    response = await client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer wrong"},
        json=SAMPLE_START_ENVELOPE,
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_hook_is_acknowledged_once(
    client_and_world: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """A replayed event ID does not reach the world service twice."""
    client, world = client_and_world

    first = await client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer hook-secret"},
        json=SAMPLE_START_ENVELOPE,
    )
    second = await client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer hook-secret"},
        json=SAMPLE_START_ENVELOPE,
    )

    assert first.json() == {"accepted": True}
    assert second.json() == {"accepted": False}
    assert world.ingest_hook.await_count == 1


@pytest.mark.asyncio
async def test_hook_rejects_sensitive_extra(
    client_and_world: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """Credentials and raw tool payloads cannot enter the observability bridge."""
    client, world = client_and_world
    unsafe_envelope = {
        **SAMPLE_START_ENVELOPE,
        "extra": {
            **SAMPLE_EXTRA,
            "raw_tool_result": "x" * 20_001,
            "api_key": "not-accepted",
        },
    }

    response = await client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer hook-secret"},
        json=unsafe_envelope,
    )

    assert response.status_code == 422
    assert world.ingest_hook.await_count == 0


@pytest.mark.asyncio
async def test_hook_rejects_overlong_allowed_extra(
    client_and_world: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    """An allowed field remains bounded before it reaches the world service."""
    client, world = client_and_world
    oversized_envelope = {
        **SAMPLE_START_ENVELOPE,
        "extra": {
            **SAMPLE_EXTRA,
            "child_goal": "x" * 1_001,
        },
    }

    response = await client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer hook-secret"},
        json=oversized_envelope,
    )

    assert response.status_code == 422
    assert world.ingest_hook.await_count == 0


@pytest.mark.asyncio
async def test_hook_is_not_exposed_without_a_token() -> None:
    """Optional hook integration is absent unless the operator configures a token."""
    app = create_app(runtime=cast("AppRuntime", HookRuntime(None)))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/integrations/hermes/events", json=SAMPLE_START_ENVELOPE)

    assert response.status_code == 404
