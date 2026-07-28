import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from yume_api.services.session import SessionService, SessionStateError

WRITE_FAILURE_MESSAGE = "write failed"
CLEANUP_FAILURE_MESSAGE = "cleanup failed"


@pytest.fixture
def fake_client() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_ensure_session_reuses_the_created_id(tmp_path: Path, fake_client: AsyncMock) -> None:
    service = SessionService(fake_client, tmp_path / "state.json")
    fake_client.create_session.return_value = "session-1"

    first = await service.ensure_session()
    second = await service.ensure_session()

    assert first == second == "session-1"
    assert (tmp_path / "state.json").read_text("utf-8") == '{"session_id":"session-1"}'
    fake_client.create_session.assert_awaited_once_with("Yume Dashboard")


@pytest.mark.asyncio
async def test_ensure_session_reuses_a_persisted_id(tmp_path: Path, fake_client: AsyncMock) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"session_id":"session-1"}', encoding="utf-8")
    service = SessionService(fake_client, state_path)

    session_id = await service.ensure_session()

    assert session_id == "session-1"
    fake_client.create_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_session_creates_once_when_called_concurrently(
    tmp_path: Path, fake_client: AsyncMock
) -> None:
    service = SessionService(fake_client, tmp_path / "state.json")
    fake_client.create_session.return_value = "session-1"

    session_ids = await asyncio.gather(service.ensure_session(), service.ensure_session())

    assert session_ids == ["session-1", "session-1"]
    fake_client.create_session.assert_awaited_once_with("Yume Dashboard")


@pytest.mark.asyncio
async def test_reset_session_replaces_state_atomically(
    tmp_path: Path, fake_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "nested" / "state.json"
    service = SessionService(fake_client, state_path)
    fake_client.create_session.side_effect = ["session-1", "session-2"]
    original_replace = Path.replace
    replacements: list[tuple[str, str]] = []

    def check_then_replace(source: Path, destination: Path) -> Path:
        replacements.append(
            (
                Path(source).read_text("utf-8"),
                Path(destination).read_text("utf-8") if Path(destination).exists() else "",
            )
        )
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", check_then_replace)

    await service.ensure_session()
    replacement = await service.reset_session()

    assert replacement == "session-2"
    assert json.loads(state_path.read_text("utf-8")) == {"session_id": "session-2"}
    assert replacements == [
        ('{"session_id":"session-1"}', ""),
        ('{"session_id":"session-2"}', '{"session_id":"session-1"}'),
    ]


@pytest.mark.asyncio
async def test_ensure_session_rejects_malformed_persisted_state(
    tmp_path: Path, fake_client: AsyncMock
) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"session_id": 42}', encoding="utf-8")
    service = SessionService(fake_client, state_path)

    with pytest.raises(SessionStateError, match="invalid session state"):
        await service.ensure_session()

    fake_client.create_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_temporary_file_cleanup_does_not_mask_persistence_error(
    tmp_path: Path, fake_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = SessionService(fake_client, tmp_path / "state.json")
    fake_client.create_session.return_value = "session-1"

    def fail_write_text(*_: object, **__: object) -> int:
        raise OSError(WRITE_FAILURE_MESSAGE)

    def fail_unlink(*_: object, **__: object) -> None:
        raise OSError(CLEANUP_FAILURE_MESSAGE)

    monkeypatch.setattr(Path, "write_text", fail_write_text)
    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(SessionStateError, match="could not persist session state"):
        await service.ensure_session()
