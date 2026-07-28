"""Live world-event WebSocket endpoint."""

from fastapi import APIRouter, WebSocket

from yume_api.contracts.factories import make_snapshot_event

router = APIRouter(prefix="/api")


@router.websocket("/events")
async def events(websocket: WebSocket) -> None:
    """Send a replacement snapshot before all subsequently published world events."""
    world = websocket.app.state.world
    snapshot, subscription = world.subscribe()
    try:
        await websocket.accept()
        await websocket.send_json(make_snapshot_event(snapshot).model_dump(mode="json"))
        async for event in subscription:
            await websocket.send_json(event.model_dump(mode="json"))
    finally:
        await subscription.aclose()
