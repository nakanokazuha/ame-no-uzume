"""Browser-safe REST API routes for the authoritative world service."""

import asyncio
import logging
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Header, HTTPException, Path, Request, status
from pydantic import BaseModel, Field, StrictBool, StrictStr

from yume_api.assets.models import PackManifest
from yume_api.contracts.events import WorldSnapshot
from yume_api.hermes.models import HermesCapabilities
from yume_api.integrations.hook_models import HookEnvelope
from yume_api.integrations.hook_receiver import HookReceiver
from yume_api.services.world import (
    TASK_ALREADY_RUNNING_MESSAGE,
    WorldService,
    WorldTaskReservation,
)

router = APIRouter(prefix="/api")
hook_router = APIRouter()
MAX_TASK_TEXT_LENGTH = 20_000
MAX_IDENTIFIER_LENGTH = 200
logger = logging.getLogger(__name__)


class HermesCommands(Protocol):
    """Capability-gated Hermes mutations available to browser routes."""

    async def stop_run(self, run_id: str) -> None:
        """Request that one Hermes run stops."""

    async def resolve_approval(self, run_id: str, approval_id: str, *, approved: bool) -> None:
        """Resolve one pending Hermes approval."""


class HookEvents(Protocol):
    """Bounded hook events accepted by the next observability enhancement step."""

    async def ingest_hook(self, envelope: HookEnvelope) -> None:
        """Ingest one authenticated, deduplicated hook envelope."""


class BootstrapResponse(BaseModel):
    """Everything the browser needs before opening the event socket."""

    world: WorldSnapshot
    asset_pack: PackManifest


class TaskRequest(BaseModel):
    """Text-only task input accepted by the v1 dashboard."""

    text: StrictStr = Field(min_length=1, max_length=MAX_TASK_TEXT_LENGTH)


class ApprovalDecision(BaseModel):
    """A single browser decision for a capability-advertised approval."""

    approval_id: StrictStr = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    approved: StrictBool


def _world(request: Request) -> WorldService:
    try:
        return request.app.state.world
    except AttributeError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "dashboard runtime is unavailable"
        ) from error


def _capabilities(request: Request) -> HermesCapabilities:
    return request.app.state.capabilities


def _hermes(request: Request) -> HermesCommands:
    return request.app.state.hermes


def _hook_receiver(request: Request) -> HookReceiver:
    try:
        return request.app.state.hook_receiver
    except AttributeError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hook ingestion is unavailable") from error


def _hook_events(request: Request) -> HookEvents:
    return cast("HookEvents", _world(request))


@router.get("/bootstrap")
async def bootstrap(request: Request) -> BootstrapResponse:
    """Return a coherent snapshot plus the validated declarative asset pack."""
    return BootstrapResponse(
        world=_world(request).snapshot(), asset_pack=request.app.state.asset_pack
    )


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def submit_task(body: TaskRequest, request: Request) -> dict[str, str]:
    """Start a background text stream after rejecting whitespace-only input."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "task text cannot be blank")
    background_tasks: set[asyncio.Task[object]] = request.app.state.background_tasks
    try:
        reservation = await _world(request).reserve_task()
    except RuntimeError as error:
        if str(error) == TASK_ALREADY_RUNNING_MESSAGE:
            raise HTTPException(status.HTTP_409_CONFLICT, TASK_ALREADY_RUNNING_MESSAGE) from error
        raise
    try:
        task = asyncio.create_task(reservation.submit_task(text))
    except Exception:
        reservation.close()
        raise
    background_tasks.add(task)
    task.add_done_callback(
        lambda completed_task: _complete_background_task(
            completed_task, background_tasks, reservation
        )
    )
    return {"status": "accepted"}


@router.post("/session/reset")
async def reset_session(request: Request) -> dict[str, str]:
    """Replace the one persisted dashboard transcript."""
    try:
        session_id = await _world(request).reset_session()
    except RuntimeError as error:
        if str(error) == TASK_ALREADY_RUNNING_MESSAGE:
            raise HTTPException(status.HTTP_409_CONFLICT, TASK_ALREADY_RUNNING_MESSAGE) from error
        raise
    return {"session_id": session_id}


@router.post("/runs/{run_id}/stop")
async def stop_run(
    run_id: Annotated[str, Path(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)], request: Request
) -> dict[str, str]:
    """Request a stop only when Hermes advertises that operation."""
    if not _capabilities(request).run_stop:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Hermes run stop is unavailable")
    await _hermes(request).stop_run(run_id)
    return {"status": "stopped"}


@router.post("/runs/{run_id}/approval")
async def resolve_approval(
    run_id: Annotated[str, Path(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)],
    body: ApprovalDecision,
    request: Request,
) -> dict[str, str]:
    """Resolve an approval only when Hermes advertises that operation."""
    if not _capabilities(request).run_approval:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Hermes run approval is unavailable")
    await _hermes(request).resolve_approval(run_id, body.approval_id, approved=body.approved)
    return {"status": "resolved"}


@hook_router.post("/integrations/hermes/events")
async def ingest_hook(
    envelope: HookEnvelope,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    """Authenticate, deduplicate, and forward a bounded Hermes lifecycle event."""
    receiver = _hook_receiver(request)
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        receiver.authenticate(token)
    except PermissionError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid hook token") from error
    if not receiver.accept(envelope):
        return {"accepted": False}
    await _hook_events(request).ingest_hook(envelope)
    return {"accepted": True}


def _complete_background_task(
    task: asyncio.Task[object],
    background_tasks: set[asyncio.Task[object]],
    reservation: WorldTaskReservation,
) -> None:
    """Discard a completed task after observing and logging a stream failure."""
    background_tasks.discard(task)
    reservation.close()
    if task.cancelled():
        return
    try:
        task.result()
    except Exception:
        logger.exception("dashboard task stream failed")
