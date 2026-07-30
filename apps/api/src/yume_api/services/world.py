"""Authoritative world orchestration for browser commands and Hermes streams."""

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from yume_api.contracts.events import ConversationMessage, WorldEvent, WorldSnapshot
from yume_api.contracts.factories import (
    make_connection_changed,
    make_snapshot_event,
    make_user_message,
)
from yume_api.domain.reducer import WorldReducer
from yume_api.hermes.models import HermesCapabilities, HermesJob, HermesStreamEvent
from yume_api.services.jobs import JobSynchronizer

SUBSCRIBER_QUEUE_SIZE = 100
TASK_ALREADY_RUNNING_MESSAGE = "a task is already running"
INVALID_SUBSCRIBER_QUEUE_SIZE_MESSAGE = "subscriber queue size must be positive"
NOT_FOUND_STATUS_CODE = 404
JOB_POLL_INTERVAL_SECONDS = 60


class WorldSession(Protocol):
    """Persistent-session operations owned by the world service."""

    async def ensure_session(self) -> str:
        """Return the active persisted session ID."""

    async def reset_session(self) -> str:
        """Replace the active persisted session and return its ID."""


class WorldClient(Protocol):
    """Hermes operations needed to hydrate, stream, and discover dashboard work."""

    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        """Return the persisted dashboard transcript."""

    def stream_task(
        self,
        capabilities: HermesCapabilities,
        session_id: str,
        text: str,
        history: list[ConversationMessage],
    ) -> AsyncIterator[HermesStreamEvent]:
        """Yield Hermes events for one task."""

    async def list_jobs(self) -> list[HermesJob]:
        """Return the verified scheduled jobs currently known to Hermes."""


class WorldNormalizer(Protocol):
    """Transform raw Hermes stream messages into ordered world events."""

    def reset(self) -> None:
        """Clear task-local normalizer state."""

    def normalize(self, event: HermesStreamEvent, sequence: int) -> list[WorldEvent]:
        """Return zero or more normalized events for one raw event."""


class WorldSubscription:
    """One queue-backed event stream with deterministic cleanup."""

    def __init__(
        self, subscribers: set[asyncio.Queue[WorldEvent]], queue: asyncio.Queue[WorldEvent]
    ) -> None:
        self._subscribers = subscribers
        self._queue = queue
        self._closed = False

    def __aiter__(self) -> "WorldSubscription":
        return self

    async def __anext__(self) -> WorldEvent:
        if self._closed:
            raise StopAsyncIteration
        return await self._queue.get()

    async def aclose(self) -> None:
        """Remove this queue even when no event iteration has begun."""
        if not self._closed:
            self._closed = True
            self._subscribers.discard(self._queue)


class WorldTaskReservation:
    """A task-lock claim made before a browser request is acknowledged."""

    def __init__(self, service: "WorldService") -> None:
        self._service = service
        self._closed = False

    async def submit_task(self, text: str) -> str:
        """Run the reserved task and release its lock when the stream finishes."""
        if self._closed:
            raise RuntimeError(TASK_ALREADY_RUNNING_MESSAGE)
        self._closed = True
        try:
            return await self._service.run_reserved_task(text)
        finally:
            self._service.release_task_reservation()

    def close(self) -> None:
        """Release an unused reservation, including a pre-start task cancellation."""
        if not self._closed:
            self._closed = True
            self._service.release_task_reservation()


class WorldService:
    """Reduce, persist, and broadcast the one authoritative dashboard world."""

    def __init__(  # noqa: PLR0913
        self,
        session: WorldSession,
        client: WorldClient,
        normalizer: WorldNormalizer,
        reducer: WorldReducer,
        capabilities: HermesCapabilities,
        *,
        subscriber_queue_size: int = SUBSCRIBER_QUEUE_SIZE,
    ) -> None:
        if subscriber_queue_size < 1:
            raise ValueError(INVALID_SUBSCRIBER_QUEUE_SIZE_MESSAGE)
        self._session = session
        self._client = client
        self._normalizer = normalizer
        self._reducer = reducer
        self._capabilities = capabilities
        self._subscriber_queue_size = subscriber_queue_size
        self._jobs = JobSynchronizer()
        self._subscribers: set[asyncio.Queue[WorldEvent]] = set()
        self._task_lock = asyncio.Lock()

    def snapshot(self) -> WorldSnapshot:
        """Return an isolated copy of the authoritative world state."""
        return self._reducer.snapshot

    def set_capabilities(self, capabilities: HermesCapabilities) -> None:
        """Use freshly discovered Hermes capabilities for subsequent task streams."""
        self._capabilities = capabilities

    def subscriber_count(self) -> int:
        """Return the number of active browser event subscriptions."""
        return len(self._subscribers)

    async def hydrate(self) -> None:
        """Seed state from the persisted session, replacing a stale session once."""
        session_id = await self._session.ensure_session()
        try:
            conversation = await self._client.get_session_messages(session_id)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != NOT_FOUND_STATUS_CODE:
                raise
            session_id = await self._session.reset_session()
            conversation = []
        self._replace_snapshot(session_id, conversation, sequence=self._reducer.snapshot.sequence)

    async def reconnect(self, capabilities: HermesCapabilities) -> None:
        """Resynchronize Hermes state and publish the recovered connection to browsers."""
        self.set_capabilities(capabilities)
        await self.hydrate()
        recovered_snapshot = self._reducer.snapshot.model_copy(
            deep=True,
            update={
                "connection": "connected",
                "sequence": self._reducer.snapshot.sequence + 1,
            },
        )
        await self.publish(make_snapshot_event(recovered_snapshot))

    async def poll_jobs(self) -> None:
        """Continuously reconcile confirmed Hermes scheduled jobs into the world."""
        while True:
            try:
                jobs = await self._client.list_jobs()
                for event in self._jobs.reconcile(
                    jobs, self.snapshot(), self._reducer.snapshot.sequence + 1
                ):
                    await self.publish(event)
            except (ValueError, httpx.RequestError, httpx.HTTPStatusError) as error:
                await self.publish(
                    make_connection_changed(
                        "degraded", str(error), self._reducer.snapshot.sequence + 1
                    )
                )
            await asyncio.sleep(JOB_POLL_INTERVAL_SECONDS)

    def subscribe(self) -> tuple[WorldSnapshot, WorldSubscription]:
        """Return one snapshot and a subscription registered before any later event.

        This method intentionally has no await points between registering its queue
        and copying the snapshot. In the single event loop serving the dashboard,
        that makes the snapshot/live handoff atomic: events are either in the
        snapshot or queued for the returned stream.
        """
        queue: asyncio.Queue[WorldEvent] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        self._subscribers.add(queue)
        snapshot = self.snapshot()

        return snapshot, WorldSubscription(self._subscribers, queue)

    async def publish(self, event: WorldEvent) -> None:
        """Apply an event and publish it without letting slow browsers grow memory."""
        self._reducer.apply(event)
        for subscriber in self._subscribers:
            if subscriber.full():
                subscriber.get_nowait()
            subscriber.put_nowait(event)

    async def submit_task(self, text: str) -> str:
        """Submit exactly one task stream, rejecting concurrent work deterministically."""
        reservation = await self.reserve_task()
        return await reservation.submit_task(text)

    async def reserve_task(self) -> WorldTaskReservation:
        """Reserve the task/reset lock before a browser task is acknowledged."""
        if self._task_lock.locked():
            raise RuntimeError(TASK_ALREADY_RUNNING_MESSAGE)
        await self._task_lock.acquire()
        return WorldTaskReservation(self)

    async def run_reserved_task(self, text: str) -> str:
        """Stream a task while its caller-owned reservation holds the task lock."""
        session_id = await self._session.ensure_session()
        history = self._reducer.snapshot.conversation
        self._normalizer.reset()
        try:
            await self.publish(make_user_message(text, self._reducer.snapshot.sequence + 1))
            async for raw_event in self._client.stream_task(
                self._capabilities, session_id, text, history
            ):
                for event in self._normalizer.normalize(
                    raw_event, self._reducer.snapshot.sequence + 1
                ):
                    await self.publish(event)
        finally:
            self._normalizer.reset()
        return session_id

    def release_task_reservation(self) -> None:
        """Release a completed or abandoned task admission reservation."""
        self._task_lock.release()

    async def reset_session(self) -> str:
        """Replace the persistent transcript unless a task is currently streaming."""
        if self._task_lock.locked():
            raise RuntimeError(TASK_ALREADY_RUNNING_MESSAGE)
        async with self._task_lock:
            session_id = await self._session.reset_session()
            replacement = self._replacement_snapshot(
                session_id, [], sequence=self._reducer.snapshot.sequence + 1
            )
            await self.publish(make_snapshot_event(replacement))
        return session_id

    def _replace_snapshot(
        self, session_id: str, conversation: list[ConversationMessage], *, sequence: int
    ) -> None:
        self._reducer.apply(
            make_snapshot_event(self._replacement_snapshot(session_id, conversation, sequence))
        )

    def _replacement_snapshot(
        self, session_id: str, conversation: list[ConversationMessage], sequence: int
    ) -> WorldSnapshot:
        snapshot = self._reducer.snapshot
        return WorldSnapshot(
            sequence=sequence,
            connection=snapshot.connection,
            telemetry_mode=snapshot.telemetry_mode,
            session_id=session_id,
            agents=snapshot.agents,
            conversation=conversation,
        )
