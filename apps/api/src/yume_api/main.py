"""FastAPI application factory and startup wiring for the Yume backend."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx
import yaml
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.staticfiles import StaticFiles

from yume_api.api.diagnostics import Diagnostic
from yume_api.api.diagnostics import router as diagnostics_router
from yume_api.api.routes import HermesCommands
from yume_api.api.routes import router as api_router
from yume_api.api.websocket import router as websocket_router
from yume_api.assets.models import PackManifest
from yume_api.assets.validator import AssetPackError, load_and_validate_pack
from yume_api.config.loader import load_dashboard_config
from yume_api.config.models import DashboardConfig
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.client import HermesClient
from yume_api.hermes.models import HermesCapabilities
from yume_api.services.session import SessionService
from yume_api.services.world import WorldService

DEFAULT_CONFIG_PATH = Path("config/dashboard.example.yaml")
DEFAULT_ASSET_PACK_ROOT = Path("asset-packs")
DEFAULT_WEB_DIST = Path("apps/web/dist")
PROJECT_ROOT = Path(__file__).resolve().parents[4]
SESSION_STATE_FILENAME = "yume-session.json"


@dataclass(slots=True)
class AppRuntime:
    """The server-only dependencies that back browser-facing API routes."""

    hermes: HermesCommands
    world: WorldService
    capabilities: HermesCapabilities
    asset_pack: PackManifest
    close_hermes: bool = False


def _build_runtime(config: DashboardConfig, asset_pack: PackManifest) -> AppRuntime:
    """Construct live services after validated configuration and assets are available."""
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


def _runtime_paths() -> tuple[Path, Path, Path]:
    """Return process-level locations without introducing a settings dependency early."""
    return (
        Path(os.environ.get("YUME_DASHBOARD_CONFIG", DEFAULT_CONFIG_PATH)),
        Path(os.environ.get("YUME_ASSET_PACK_ROOT", DEFAULT_ASSET_PACK_ROOT)),
        Path(os.environ.get("YUME_WEB_DIST", DEFAULT_WEB_DIST)),
    )


def _mount_static_resources(app: FastAPI) -> None:
    """Serve declarative asset packs and the built browser application after API routes."""
    _, asset_pack_root, web_dist = _runtime_paths()
    app.mount(
        "/asset-packs",
        StaticFiles(directory=_workspace_path(asset_pack_root), check_dir=True),
        name="asset-packs",
    )
    app.mount(
        "/",
        StaticFiles(directory=_workspace_path(web_dist), html=True, check_dir=True),
        name="web",
    )


def _workspace_path(path: Path) -> Path:
    """Resolve default relative static locations from the repository at test or runtime."""
    if path.is_absolute() or path.exists():
        return path
    return PROJECT_ROOT / path


def _set_runtime_state(app: FastAPI, runtime: AppRuntime) -> None:
    """Expose a constructed runtime to the API and WebSocket route handlers."""
    app.state.hermes = runtime.hermes
    app.state.world = runtime.world
    app.state.capabilities = runtime.capabilities
    app.state.asset_pack = runtime.asset_pack


def _start_job_poller(app: FastAPI, runtime: AppRuntime) -> None:
    """Start the one job poller only after a successful Hermes synchronization."""
    if not app.state.background_tasks:
        app.state.background_tasks.add(asyncio.create_task(runtime.world.poll_jobs()))


async def _retry_hermes(app: FastAPI, runtime: AppRuntime) -> Diagnostic:
    """Refresh Hermes capabilities and the authoritative snapshot after a startup failure."""
    try:
        client = cast("HermesClient", runtime.hermes)
        capabilities = await client.get_capabilities()
        runtime.capabilities = capabilities
        app.state.capabilities = capabilities
        await runtime.world.reconnect(capabilities)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as error:
        app.state.diagnostic = Diagnostic.hermes_unavailable(error)
    else:
        app.state.diagnostic = Diagnostic.ready()
        _start_job_poller(app, runtime)
    return app.state.diagnostic


def _startup_runtime(app: FastAPI, runtime: AppRuntime | None) -> AppRuntime | None:
    """Load only expected startup inputs into a live runtime or retain a diagnostic."""
    if runtime is not None:
        return runtime
    config_path, asset_pack_root, _ = _runtime_paths()
    try:
        config = load_dashboard_config(config_path)
    except (OSError, UnicodeError, ValidationError, yaml.YAMLError) as error:
        app.state.diagnostic = Diagnostic.invalid_config(config_path, error)
        return None
    try:
        asset_pack = load_and_validate_pack(asset_pack_root / config.asset_pack)
    except AssetPackError as error:
        app.state.diagnostic = Diagnostic.invalid_assets(
            asset_pack_root / config.asset_pack / "pack.json", error
        )
        return None
    return _build_runtime(config, asset_pack)


def create_app(*, runtime: AppRuntime | None = None) -> FastAPI:
    """Create the API app; supplied runtimes keep tests off real Hermes credentials."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_runtime = _startup_runtime(app, runtime)
        if active_runtime is None:
            yield
            return

        _set_runtime_state(app, active_runtime)
        app.state.diagnostic = Diagnostic.ready()

        async def retry_hermes() -> Diagnostic:
            return await _retry_hermes(app, active_runtime)

        app.state.retry_hermes = retry_hermes
        try:
            if runtime is None:
                client = cast("HermesClient", active_runtime.hermes)
                capabilities = await client.get_capabilities()
                active_runtime.capabilities = capabilities
                app.state.capabilities = capabilities
                await active_runtime.world.reconnect(capabilities)
            else:
                await active_runtime.world.hydrate()
            _start_job_poller(app, active_runtime)
            yield
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as error:
            app.state.diagnostic = Diagnostic.hermes_unavailable(error)
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
    app.state.diagnostic = Diagnostic.ready()

    async def retry_diagnostic() -> Diagnostic:
        """Keep invalid configuration and assets diagnostic-only until they are corrected."""
        return app.state.diagnostic

    app.state.retry_hermes = retry_diagnostic
    if runtime is not None:
        _set_runtime_state(app, runtime)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    app.include_router(websocket_router)
    app.include_router(diagnostics_router)
    _mount_static_resources(app)
    return app


app = create_app()
