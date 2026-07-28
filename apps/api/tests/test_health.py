import inspect

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from yume_api.main import create_app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_is_synchronous_until_it_performs_io() -> None:
    health_route = next(
        route
        for route in create_app().routes
        if isinstance(route, APIRoute) and route.path == "/api/health"
    )

    assert not inspect.iscoroutinefunction(health_route.endpoint)
