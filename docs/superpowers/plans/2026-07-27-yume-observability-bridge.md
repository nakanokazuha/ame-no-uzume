# Yume Observability Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, authenticated Hermes shell-hook bridge that enriches delegated-worker identity and lifecycle events without becoming a dependency of the core dashboard.

**Architecture:** Hermes shell hooks run a standalone Python standard-library emitter for `subagent_start` and `subagent_stop`. FastAPI authenticates and deduplicates their envelopes, then the existing normalizer emits higher-authority domain events and switches telemetry mode from `standard` to `enhanced`.

**Tech Stack:** Hermes shell hooks, Python 3.13 standard library emitter, FastAPI, Pydantic 2, pytest, HTTPX.

## Global Constraints

- Execute only after the core dashboard plan passes its completion gate.
- The bridge is optional; removing it must leave standard telemetry fully functional.
- Hook failures must never block or modify Hermes behavior.
- The bridge endpoint is loopback-only and requires a separate `YUME_HOOK_TOKEN`.
- Raw tool results and credentials must never be transmitted.
- Hook events have higher evidence priority than session-stream events.
- A task is complete only after its verification passes, its focused commit is created, and `git push origin main` succeeds.
- Work directly on `main`; do not add CI/CD or GitHub Actions before the full v1 acceptance gate passes.

---

### Task 1: Add Authenticated, Deduplicated Hook Ingestion

**Files:**
- Create: `apps/api/src/yume_api/integrations/hook_models.py`
- Create: `apps/api/src/yume_api/integrations/hook_receiver.py`
- Modify: `apps/api/src/yume_api/api/routes.py`
- Modify: `apps/api/src/yume_api/main.py`
- Modify: `apps/api/src/yume_api/settings.py`
- Create: `apps/api/tests/integrations/test_hook_receiver.py`

**Interfaces:**
- Produces: `POST /api/integrations/hermes/events`
- Produces: `HookReceiver.accept(envelope: HookEnvelope) -> bool`

- [ ] **Step 1: Write failing authentication and deduplication tests**

```python
sample_start_envelope = {
    "schema_version": 1,
    "event_id": "hook-1",
    "occurred_at": "2026-07-27T00:00:00Z",
    "event": "subagent_start",
    "session_id": "parent-1",
    "extra": {
        "child_subagent_id": "child-7",
        "child_role": "researcher",
        "child_goal": "Compare Hermes event hooks",
    },
}


def test_hook_rejects_wrong_token(client) -> None:
    response = client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer wrong"},
        json=sample_start_envelope,
    )
    assert response.status_code == 401


def test_duplicate_hook_is_acknowledged_once(client, world) -> None:
    first = client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer hook-secret"},
        json=sample_start_envelope,
    )
    second = client.post(
        "/api/integrations/hermes/events",
        headers={"Authorization": "Bearer hook-secret"},
        json=sample_start_envelope,
    )
    assert first.json() == {"accepted": True}
    assert second.json() == {"accepted": False}
    assert world.ingest_hook.await_count == 1
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/integrations/test_hook_receiver.py -q`

Expected: FAIL because the receiver is absent.

- [ ] **Step 3: Define the minimal envelope**

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HookEnvelope(BaseModel):
    schema_version: Literal[1]
    event_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    event: Literal["subagent_start", "subagent_stop"]
    session_id: str
    extra: dict
```

- [ ] **Step 4: Implement constant-time token validation and bounded deduplication**

```python
import hmac
from cachetools import TTLCache


class HookReceiver:
    def __init__(self, expected_token: str) -> None:
        self._token = expected_token
        self._seen = TTLCache(maxsize=10_000, ttl=3600)

    def authenticate(self, token: str) -> None:
        if not hmac.compare_digest(token, self._token):
            raise PermissionError("invalid hook token")

    def accept(self, envelope: HookEnvelope) -> bool:
        if envelope.event_id in self._seen:
            return False
        self._seen[envelope.event_id] = True
        return True
```

- [ ] **Step 5: Implement the route**

```python
@router.post("/integrations/hermes/events")
async def ingest_hook(
    envelope: HookEnvelope,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
):
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        request.app.state.hook_receiver.authenticate(token)
    except PermissionError:
        raise HTTPException(401, "invalid hook token")
    if not request.app.state.hook_receiver.accept(envelope):
        return {"accepted": False}
    await request.app.state.world.ingest_hook(envelope)
    return {"accepted": True}
```

Add `hook_token: SecretStr | None = None` to `Settings`. Register this router and create `HookReceiver` only when the token is non-empty:

```python
if settings.hook_token is not None:
    app.state.hook_receiver = HookReceiver(settings.hook_token.get_secret_value())
    app.include_router(hook_router, prefix="/api")
```

When disabled, the endpoint returns 404 rather than accepting unauthenticated events.

- [ ] **Step 6: Verify and commit**

Run: `uv run --package yume-api pytest apps/api/tests/integrations/test_hook_receiver.py -q`

```bash
git add apps/api/src/yume_api/integrations apps/api/src/yume_api/api/routes.py apps/api/src/yume_api/settings.py apps/api/tests/integrations
git commit -m "feat: ingest authenticated Hermes hook events"
```

### Task 2: Normalize Enhanced Subagent Lifecycle Events

**Files:**
- Modify: `apps/api/src/yume_api/domain/normalizer.py`
- Modify: `apps/api/src/yume_api/services/world.py`
- Create: `apps/api/tests/domain/test_hook_normalizer.py`

**Interfaces:**
- Consumes: `HookEnvelope`
- Produces: enhanced `agent.spawned`, `agent.state_changed`, and `agent.removed`

- [ ] **Step 1: Write failing start/stop normalization tests**

```python
start_envelope = HookEnvelope.model_validate({
    "schema_version": 1,
    "event_id": "hook-1",
    "occurred_at": "2026-07-27T00:00:00Z",
    "event": "subagent_start",
    "session_id": "parent-1",
    "extra": {
        "child_subagent_id": "child-7",
        "child_role": "researcher",
        "child_goal": "Compare Hermes event hooks",
    },
})
failed_stop_envelope = HookEnvelope.model_validate({
    **start_envelope.model_dump(mode="json"),
    "event_id": "hook-2",
    "event": "subagent_stop",
    "extra": {"child_subagent_id": "child-7", "child_status": "failed"},
})


def test_subagent_start_uses_verified_role_and_goal() -> None:
    events = normalizer.normalize_hook(start_envelope, sequence=20)
    spawned = events[0]
    assert spawned.agent_id == "delegated:child-7"
    assert spawned.payload.display_name == "Researcher"
    assert spawned.payload.task_summary == "Compare Hermes event hooks"
    assert spawned.evidence == "verified"


def test_subagent_stop_preserves_failure_status() -> None:
    events = normalizer.normalize_hook(failed_stop_envelope, sequence=21)
    assert [event.payload.status for event in events if event.type == "agent.state_changed"] == ["failed"]
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/domain/test_hook_normalizer.py -q`

Expected: FAIL because hook normalization is absent.

- [ ] **Step 3: Implement bounded verified enrichment**

```python
def normalize_hook(self, envelope: HookEnvelope, sequence: int) -> list[WorldEvent]:
    if envelope.event == "subagent_start":
        child_id = str(envelope.extra["child_subagent_id"])
        role = envelope.extra.get("child_role")
        goal = envelope.extra.get("child_goal")
        return [
            make_agent_spawned(
                agent_id=f"delegated:{child_id}",
                display_name=humanize_role(role) if role else "Delegated Worker",
                task_summary=truncate(goal, 240) if goal else None,
                room="lobby",
                evidence="verified",
                source="hermes.hook",
                sequence=sequence,
            )
        ]
    status = envelope.extra.get("child_status", "error")
    return make_subagent_exit_events(
        agent_id=f"delegated:{envelope.extra['child_subagent_id']}",
        failed=status not in {"completed"},
        sequence=sequence,
        source="hermes.hook",
    )
```

Never forward `tool_call_history` inputs or child summaries into the inspector. Use tool names only for room selection.

- [ ] **Step 4: Switch snapshots to enhanced telemetry after the first accepted hook**

```python
async def ingest_hook(self, envelope: HookEnvelope) -> None:
    if self._reducer.snapshot.telemetry_mode != "enhanced":
        snapshot = self._reducer.snapshot.model_copy(
            update={"telemetry_mode": "enhanced"}, deep=True
        )
        await self.publish(make_snapshot_event(snapshot))
    for event in self._normalizer.normalize_hook(
        envelope, self._reducer.snapshot.sequence + 1
    ):
        await self.publish(event)
```

No code path assigns `standard` after application startup.

- [ ] **Step 5: Verify and commit**

Run: `uv run --package yume-api pytest apps/api/tests/domain/test_hook_normalizer.py -q`

```bash
git add apps/api/src/yume_api/domain/normalizer.py apps/api/src/yume_api/services/world.py apps/api/tests/domain/test_hook_normalizer.py
git commit -m "feat: enrich delegated workers from Hermes hooks"
```

### Task 3: Build the Host-Side Shell-Hook Emitter

**Files:**
- Create: `integrations/hermes-hook/emit.py`
- Create: `integrations/hermes-hook/config.example.yaml`
- Create: `integrations/hermes-hook/install.sh`
- Create: `integrations/hermes-hook/tests/test_emit.py`
- Create: `integrations/hermes-hook/README.md`

**Interfaces:**
- Consumes: Hermes shell-hook JSON on stdin
- Produces: authenticated event POST and `{}` on stdout

- [ ] **Step 1: Write the failing emitter test**

```python
def test_subagent_start_payload_is_minimal(monkeypatch) -> None:
    sent = capture_request(monkeypatch)
    result = emit(
        "subagent_start",
        {
            "session_id": "parent-1",
            "extra": {
                "child_subagent_id": "child-7",
                "child_role": "researcher",
                "child_goal": "Compare hooks",
                "api_key": "must-not-leak",
            },
        },
    )
    assert result == {}
    assert sent["extra"] == {
        "child_subagent_id": "child-7",
        "child_role": "researcher",
        "child_goal": "Compare hooks",
    }
```

- [ ] **Step 2: Implement the non-blocking standard-library emitter**

```python
#!/usr/bin/env python3
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from urllib.request import Request, urlopen

ALLOWED = {
    "subagent_start": {"child_subagent_id", "child_role", "child_goal"},
    "subagent_stop": {
        "child_subagent_id", "child_role", "child_status", "duration_ms",
        "tool_call_history",
    },
}


def emit(event: str, payload: dict) -> dict:
    extra = {
        key: value
        for key, value in payload.get("extra", {}).items()
        if key in ALLOWED[event]
    }
    if "tool_call_history" in extra:
        extra["tool_call_history"] = [
            {"tool_name": item.get("tool_name"), "status": item.get("status")}
            for item in extra["tool_call_history"]
        ]
    envelope = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "event": event,
        "session_id": payload.get("session_id", ""),
        "extra": extra,
    }
    request = Request(
        os.environ["YUME_HOOK_URL"],
        data=json.dumps(envelope).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['YUME_HOOK_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urlopen(request, timeout=1).read()
    except Exception:
        pass
    return {}


if __name__ == "__main__":
    print(json.dumps(emit(sys.argv[1], json.load(sys.stdin))))
```

- [ ] **Step 3: Add exact Hermes configuration**

```yaml
hooks:
  subagent_start:
    - command: "~/.hermes/agent-hooks/yume-observer.py subagent_start"
      timeout: 2
  subagent_stop:
    - command: "~/.hermes/agent-hooks/yume-observer.py subagent_stop"
      timeout: 2
```

The installer copies the emitter to `~/.hermes/agent-hooks/yume-observer.py`, sets mode `0700`, and prints the YAML block. It does not edit Hermes configuration automatically.

- [ ] **Step 4: Verify with Hermes hook diagnostics**

Run:

```bash
hermes hooks doctor
hermes hooks test subagent_start --payload-file integrations/hermes-hook/tests/fixtures/start.json
```

Expected: valid JSON output `{}`, execution below two seconds, and one accepted dashboard event.

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-hook
git commit -m "feat: add optional Hermes observability emitter"
```

### Task 4: Add Enhanced-Telemetry End-to-End Coverage

**Files:**
- Modify: `tests/e2e/dashboard.spec.ts`
- Modify: `tests/fake_hermes/app.py`
- Create: `tests/fake_hermes/fixtures/hook-start.json`
- Modify: `README.md`

**Interfaces:**
- Produces: verified enhanced mode from hook to inspector

- [ ] **Step 1: Add a failing browser test**

```ts
import startEnvelope from "../fake_hermes/fixtures/hook-start.json";

test("enhanced telemetry shows verified role and goal", async ({ page, request }) => {
  await page.goto("http://127.0.0.1:8000");
  await request.post("http://127.0.0.1:8000/api/integrations/hermes/events", {
    headers: { Authorization: "Bearer hook-secret" },
    data: startEnvelope,
  });
  await expect(page.getByText("Telemetry: enhanced")).toBeVisible();
  await expect(page.getByText("Researcher")).toBeVisible();
  await expect(page.getByText("Compare Hermes event hooks")).toBeVisible();
});
```

- [ ] **Step 2: Run and verify failure**

Run: `pnpm e2e --grep "enhanced telemetry"`

Expected: FAIL until the test profile enables the hook token.

- [ ] **Step 3: Wire the test token and document opt-in**

```yaml
services:
  dashboard-e2e:
    environment:
      YUME_HOOK_TOKEN: hook-secret
```

Add README commands for shell-hook consent, `hermes hooks doctor`, local endpoint and token setup, and removal. State explicitly that omitting `YUME_HOOK_TOKEN` disables the receiver route and leaves standard mode fully supported.

- [ ] **Step 4: Run full verification and commit**

Run:

```bash
make lint
make test
pnpm e2e
```

Expected: all pass.

```bash
git add tests README.md
git commit -m "test: verify enhanced Hermes telemetry"
```
