"""FastAPI application factory and startup wiring for the Yume backend."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi import FastAPI

from yume_api.api.routes import HermesCommands
from yume_api.api.routes import router as api_router
from yume_api.api.websocket import router as websocket_router
from yume_api.assets.models import PackManifest
from yume_api.assets.validator import load_and_validate_pack
from yume_api.config.loader import load_dashboard_config
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.client import HermesClient
from yume_api.hermes.models import HermesCapabilities
from yume_api.services.session import SessionService
from yume_api.services.world import WorldService

DEFAULT_CONFIG_PATH = Path("config/dashboard.example.yaml")
DEFAULT_ASSET_PACK_ROOT = Path("asset-packs")
SESSION_STATE_FILENAME = "yume-session.json"


@dataclass(slots=True)
class AppRuntime:
    """The server-only dependencies that back browser-facing API routes."""

    hermes: HermesCommands
    world: WorldService
    capabilities: HermesCapabilities
    asset_pack: PackManifest
    close_hermes: bool = False


def _build_runtime() -> AppRuntime:
    config_path = Path(os.environ.get("YUME_DASHBOARD_CONFIG", DEFAULT_CONFIG_PATH))
    config = load_dashboard_config(config_path)
    asset_pack_root = Path(os.environ.get("YUME_ASSET_PACK_ROOT", DEFAULT_ASSET_PACK_ROOT))
    asset_pack = load_and_validate_pack(asset_pack_root / config.asset_pack)
    hermes = HermesClient(config.hermes_base_url, os.environ["HERMES_API_KEY"])
    session = SessionService(hermes, Path(config.data_dir) / SESSION_STATE_FILENAME)
    normalizer = HermesNormalizer(
        RoomPolicy([(rule.pattern, rule.room) for rule in config.room_rules])
    )
    capabilities = HermesCapabilities()
    world = WorldService(session, hermes, normalizer, WorldReducer(), capabilities)
    return AppRuntime(
        hermes=hermes,
        world=world,
        capabilities=capabilities,
        asset_pack=asset_pack,
        close_hermes=True,
    )


def create_app(*, runtime: AppRuntime | None = None) -> FastAPI:
    """Create the API app; supplied runtimes keep tests off real Hermes credentials."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_runtime = runtime or _build_runtime()
        app.state.hermes = active_runtime.hermes
        app.state.world = active_runtime.world
        app.state.capabilities = active_runtime.capabilities
        app.state.asset_pack = active_runtime.asset_pack
        try:
            if runtime is None:
                client = cast("HermesClient", active_runtime.hermes)
                capabilities = await client.get_capabilities()
                active_runtime.capabilities = capabilities
                active_runtime.world.set_capabilities(capabilities)
                app.state.capabilities = capabilities
            await active_runtime.world.hydrate()
            app.state.background_tasks.add(asyncio.create_task(active_runtime.world.poll_jobs()))
            yield
        finally:
            background_tasks: set[asyncio.Task[object]] = app.state.background_tasks
            for task in tuple(background_tasks):
                task.cancel()
            if background_tasks:
                await asyncio.gather(*background_tasks, return_exceptions=True)
            if active_runtime.close_hermes:
                await cast("HermesClient", active_runtime.hermes).aclose()

    app = FastAPI(title="Ame-no-Uzume", lifespan=lifespan)
    app.state.background_tasks = set()
    app.state.task_submission_lock = asyncio.Lock()
    if runtime is not None:
        app.state.hermes = runtime.hermes
        app.state.world = runtime.world
        app.state.capabilities = runtime.capabilities
        app.state.asset_pack = runtime.asset_pack

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    app.include_router(websocket_router)
    return app


app = create_app()
