import asyncio
import json
import logging
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, StrictStr, ValidationError

SESSION_TITLE = "Yume Dashboard"
INVALID_STATE_MESSAGE = "invalid session state"
PERSISTENCE_FAILURE_MESSAGE = "could not persist session state"
INVALID_SESSION_ID_MESSAGE = "Hermes returned an invalid session ID"
TEMPORARY_STATE_CLEANUP_MESSAGE = "could not remove failed session state temporary file"
logger = logging.getLogger(__name__)


class SessionClient(Protocol):
    """Minimal Hermes API surface needed to create dashboard sessions."""

    async def create_session(self, title: str) -> str:
        """Create a persistent Hermes session and return its ID."""


class SessionStateError(RuntimeError):
    """Raised when the persisted dashboard session state cannot be used."""


class _SessionState(BaseModel):
    session_id: StrictStr = Field(min_length=1)


class SessionService:
    """Create, reuse, and atomically replace Yume's one Hermes session."""

    def __init__(self, client: SessionClient, state_path: Path) -> None:
        self._client = client
        self._state_path = state_path
        self._session_id: str | None = None
        self._lock = asyncio.Lock()

    async def ensure_session(self) -> str:
        """Return the active persisted session, creating it exactly once when absent."""
        async with self._lock:
            if self._session_id is not None:
                return self._session_id
            persisted_session_id = await asyncio.to_thread(_read_session_id, self._state_path)
            if persisted_session_id is not None:
                self._session_id = persisted_session_id
                return persisted_session_id
            session_id = await self._client.create_session(SESSION_TITLE)
            _validate_session_id(session_id)
            await asyncio.to_thread(_persist_session_id, self._state_path, session_id)
            self._session_id = session_id
            return session_id

    async def reset_session(self) -> str:
        """Create and persist a replacement dashboard session."""
        async with self._lock:
            session_id = await self._client.create_session(SESSION_TITLE)
            _validate_session_id(session_id)
            await asyncio.to_thread(_persist_session_id, self._state_path, session_id)
            self._session_id = session_id
            return session_id


def _read_session_id(state_path: Path) -> str | None:
    if not state_path.exists():
        return None
    try:
        contents = state_path.read_text(encoding="utf-8")
        return _SessionState.model_validate(json.loads(contents)).session_id
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise SessionStateError(INVALID_STATE_MESSAGE) from error


def _persist_session_id(state_path: Path, session_id: str) -> None:
    temporary_path = state_path.with_name(f".{state_path.name}.{uuid4().hex}.tmp")
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps({"session_id": session_id}, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary_path.replace(state_path)
    except OSError as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(TEMPORARY_STATE_CLEANUP_MESSAGE)
        raise SessionStateError(PERSISTENCE_FAILURE_MESSAGE) from error


def _validate_session_id(session_id: str) -> None:
    try:
        _SessionState(session_id=session_id)
    except ValidationError as error:
        raise SessionStateError(INVALID_SESSION_ID_MESSAGE) from error
