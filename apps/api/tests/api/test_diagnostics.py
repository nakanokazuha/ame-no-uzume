from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

import yume_api.main as main_module
from yume_api.assets.models import PackManifest
from yume_api.assets.validator import AssetPackError, load_and_validate_pack
from yume_api.config.models import DashboardConfig
from yume_api.contracts.events import ConversationMessage
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.client import HermesClient
from yume_api.hermes.models import HermesCapabilities, HermesJob, HermesStreamEvent
from yume_api.main import AppRuntime, create_app
from yume_api.services.world import WorldService

STARTUP_CONNECTION_ERROR = "Hermes is starting"
RUNTIME_CONSTRUCTION_ERROR = "runtime construction failed"


class DiagnosticSession:
    async def ensure_session(self) -> str:
        return "session-1"

    async def reset_session(self) -> str:
        return "session-2"


class DiagnosticHermes:
    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        del session_id
        return []

    async def list_jobs(self) -> list[HermesJob]:
        return []

    async def stream_task(
        self,
        capabilities: HermesCapabilities,
        session_id: str,
        text: str,
        history: list[ConversationMessage],
    ) -> AsyncIterator[HermesStreamEvent]:
        del capabilities, session_id, text, history
        if False:
            yield HermesStreamEvent(event="unused", data={})

    async def stop_run(self, run_id: str) -> None:
        del run_id

    async def resolve_approval(self, run_id: str, approval_id: str, *, approved: bool) -> None:
        del run_id, approval_id, approved


class RecoveringDiagnosticHermes(DiagnosticHermes):
    def __init__(self) -> None:
        self.attempts = 0

    async def get_capabilities(self) -> HermesCapabilities:
        self.attempts += 1
        if self.attempts == 1:
            raise httpx.ConnectError(STARTUP_CONNECTION_ERROR)
        return HermesCapabilities(session_chat_stream=True)


def diagnostic_runtime() -> AppRuntime:
    hermes = DiagnosticHermes()
    return AppRuntime(
        hermes=hermes,
        world=WorldService(
            DiagnosticSession(),
            hermes,
            HermesNormalizer(RoomPolicy([])),
            WorldReducer(),
            HermesCapabilities(),
        ),
        capabilities=HermesCapabilities(),
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
    )


@pytest.mark.asyncio
async def test_build_runtime_constructs_after_validated_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_API_KEY", "test-api-key")
    asset_pack = load_and_validate_pack(Path("asset-packs/placeholder"))

    runtime = main_module._build_runtime(DashboardConfig(), asset_pack)  # noqa: SLF001

    assert isinstance(runtime.hermes, HermesClient)
    assert runtime.asset_pack == asset_pack
    await runtime.hermes.aclose()


@asynccontextmanager
async def request_client(app_runtime: AppRuntime | None = None) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(runtime=app_runtime)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_invalid_pack_still_serves_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "load_dashboard_config",
        lambda _path: DashboardConfig(asset_pack="custom"),
    )
    monkeypatch.setattr(
        main_module,
        "load_and_validate_pack",
        lambda _root: (_ for _ in ()).throw(AssetPackError("missing semantic anchors: ['lobby']")),
    )

    async with request_client() as client:
        response = await client.get("/api/diagnostics")
        retry = await client.post("/api/diagnostics/retry")

    assert response.status_code == 200
    assert response.json() == {
        "status": "invalid_assets",
        "file": "asset-packs/custom/pack.json",
        "message": "missing semantic anchors: ['lobby']",
    }
    assert retry.json() == response.json()


@pytest.mark.asyncio
async def test_runtime_construction_os_error_escapes_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "load_dashboard_config",
        lambda _path: DashboardConfig(asset_pack="placeholder"),
    )
    monkeypatch.setattr(
        main_module,
        "load_and_validate_pack",
        lambda _root: load_and_validate_pack(Path("asset-packs/placeholder")),
    )

    def raise_runtime_error(_config: DashboardConfig, _asset_pack: PackManifest) -> AppRuntime:
        raise OSError(RUNTIME_CONSTRUCTION_ERROR)

    monkeypatch.setattr(main_module, "_build_runtime", raise_runtime_error)

    with pytest.raises(OSError, match=RUNTIME_CONSTRUCTION_ERROR):
        async with request_client():
            pass


@pytest.mark.asyncio
async def test_ready_runtime_exposes_a_ready_diagnostic() -> None:
    async with request_client(diagnostic_runtime()) as client:
        response = await client.get("/api/diagnostics")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "file": None, "message": ""}


@pytest.mark.asyncio
async def test_hermes_retry_recovers_the_startup_state(monkeypatch: pytest.MonkeyPatch) -> None:
    hermes = RecoveringDiagnosticHermes()
    runtime = AppRuntime(
        hermes=hermes,
        world=WorldService(
            DiagnosticSession(),
            hermes,
            HermesNormalizer(RoomPolicy([])),
            WorldReducer(),
            HermesCapabilities(),
        ),
        capabilities=HermesCapabilities(),
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
    )
    monkeypatch.setattr(main_module, "_build_runtime", lambda _config, _asset_pack: runtime)

    async with request_client() as client:
        unavailable = await client.get("/api/diagnostics")
        recovered = await client.post("/api/diagnostics/retry")

    assert unavailable.json()["status"] == "hermes_unavailable"
    assert recovered.status_code == 200
    assert recovered.json() == {"status": "ready", "file": None, "message": ""}
    assert runtime.world.snapshot().session_id == "session-1"
    assert runtime.world.snapshot().connection == "connected"


@pytest.mark.asyncio
async def test_static_resources_serve_the_selected_pack_and_built_web_app() -> None:
    async with request_client(diagnostic_runtime()) as client:
        pack_response = await client.get("/asset-packs/placeholder/pack.json")
        web_response = await client.get("/")

    assert pack_response.status_code == 200
    assert pack_response.json()["id"] == "placeholder"
    assert web_response.status_code == 200
    assert '<div id="root"></div>' in web_response.text
