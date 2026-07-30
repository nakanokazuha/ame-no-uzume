"""Deterministic Hermes-compatible server for browser integration tests."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI(title="Fake Hermes")
FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEFAULT_SCENARIO = "auto"
SCENARIO_BY_INPUT = {
    "Research Hermes hooks": "delegated-task",
    "Stream a response": "streaming",
    "Request approval": "approval",
    "Fail this task": "failed-run",
    "Verify session reset": "session-reset",
}
_session_count = 0
_last_stream_session_id: str | None = None


def selected_scenario(input_text: str) -> str:
    """Select an explicit environment scenario or one deterministically from task input."""
    configured = os.environ.get("FAKE_HERMES_SCENARIO", DEFAULT_SCENARIO)
    if configured != DEFAULT_SCENARIO:
        return configured
    return SCENARIO_BY_INPUT.get(input_text, "streaming")


def fixture_events(scenario: str) -> list[dict[str, Any]]:
    """Load one checked-in JSONL stream fixture without accepting caller paths."""
    fixture_path = FIXTURES_DIR / f"{scenario}.jsonl"
    if not fixture_path.is_file():
        raise ValueError(f"unknown fake Hermes scenario: {scenario}")
    return [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
        if line
    ]


async def stream_fixture(scenario: str) -> AsyncIterator[str]:
    """Yield a fixture as correctly framed SSE messages with deterministic pacing."""
    for payload in fixture_events(scenario):
        delay_ms = payload.pop("delay_ms", 0)
        if delay_ms:
            await asyncio.sleep(delay_ms / 1_000)
        yield f"event: {payload['event']}\ndata: {json.dumps(payload['data'])}\n\n"


@app.get("/v1/capabilities")
async def capabilities() -> dict[str, dict[str, bool]]:
    """Advertise the native stream and capability-gated browser actions."""
    return {
        "features": {
            "session_chat_stream": True,
            "run_stop": True,
            "run_approval": True,
        }
    }


@app.post("/api/sessions")
async def create_session() -> dict[str, str]:
    """Create monotonic session IDs so reset coverage can observe replacement."""
    global _session_count
    _session_count += 1
    return {"id": f"session-e2e-{_session_count}"}


@app.get("/api/sessions/{session_id}/messages")
async def session_messages(session_id: str) -> list[dict[str, str]]:
    """Return an empty deterministic history for each test session."""
    del session_id
    return []


@app.post("/api/sessions/{session_id}/chat/stream")
async def stream_chat(session_id: str, body: dict[str, str]) -> StreamingResponse:
    """Serve the selected stream and retain its session for test-only verification."""
    global _last_stream_session_id
    _last_stream_session_id = session_id
    scenario = selected_scenario(body.get("input", ""))
    return StreamingResponse(stream_fixture(scenario), media_type="text/event-stream")


@app.get("/api/jobs")
async def list_jobs() -> list[dict[str, str]]:
    """Expose one persistent scheduled worker for deterministic discovery coverage."""
    return [
        {
            "id": "daily-memory",
            "name": "Daily memory",
            "next_run_at": "2030-01-01T00:00:00Z",
        }
    ]


@app.post("/v1/runs/{run_id}/stop", status_code=204)
async def stop_run(run_id: str) -> None:
    """Accept capability-advertised stop requests without external side effects."""
    del run_id


@app.post("/v1/runs/{run_id}/approval")
async def resolve_approval(run_id: str, body: dict[str, Any]) -> dict[str, str]:
    """Accept deterministic browser approval decisions."""
    del run_id, body
    return {"status": "resolved"}


@app.get("/__test/last-stream-session")
async def last_stream_session() -> dict[str, str | None]:
    """Expose the last stream target solely for the checked-in browser test harness."""
    return {"session_id": _last_stream_session_id}


@app.post("/__test/scenario/{scenario}")
async def set_test_scenario(scenario: str) -> dict[str, str]:
    """Set the environment-backed fixture selected by the serial browser harness."""
    fixture_events(scenario)
    os.environ["FAKE_HERMES_SCENARIO"] = scenario
    return {"scenario": scenario}
