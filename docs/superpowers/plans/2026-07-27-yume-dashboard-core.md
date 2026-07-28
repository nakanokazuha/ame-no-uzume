# Yume Core Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Before each task, apply `python-conventions`, `typescript-convention`, or both according to the files changed. Review each non-commit numbered step under Global Constraints before it is checked or advanced; the final Commit step follows its distinct pre-commit sequence, with no post-commit review.

**Goal:** Build a complete macOS-first Yume visualizer that connects one persistent Hermes session to a one-page React/Phaser office using production-shaped placeholder assets.

**Architecture:** A single FastAPI process serves the built Vite application, owns the Hermes credential, normalizes Hermes payloads into versioned domain events, and broadcasts snapshots and ordered events over WebSocket. React owns floating UI, Phaser owns the isometric world, and both consume generated TypeScript contracts plus one frontend world store.

**Tech Stack:** Python 3.13, uv, FastAPI, Pydantic 2, HTTPX, pytest, Ruff, ty; Node.js 24 LTS, pnpm, React 19, Vite 8.1, TypeScript, Phaser 4, Zustand, Vitest, Testing Library, Playwright; Docker Desktop 4.34+.

## Global Constraints

- The product is one page with no router, tabs, sidebar, pagination, settings page, or map editor.
- V1 supports one persistent, text-only `Yume Dashboard` Hermes session.
- Yume and scheduled workers persist; delegated workers are ephemeral.
- Visual detail must be verified when specific and may degrade only to generic inferred activity.
- Unknown tools map to the work floor.
- Hermes remains native and bound to `127.0.0.1`; its API key never reaches the browser or logs.
- Production is one non-root Docker container using Docker Desktop host networking.
- Placeholder and production packs use 64×32 isometric tiles and 32×48 character canvases.
- Asset packs are read-only data and artwork; they contain no executable browser code.
- The optional Hermes observability hook is not required by this plan.
- Python tasks must load `python-conventions`; TypeScript, TSX, and related JavaScript tasks must load `typescript-convention`; mixed tasks must load both.
- Every `gpt-5.6-terra` and `gpt-5.6-sol` agent uses `high` reasoning, including implementation and correction subagents plus initial, re-review, and final accumulated-diff reviewers; reserve `xhigh` for a future Luna agent only.
- Each non-commit numbered step must be reviewed before it is checked or advanced: dispatch a fresh read-only `gpt-5.6-sol` reviewer using `superpowers:requesting-code-review`.
- Valid Critical or Important findings go to a fresh `gpt-5.6-terra` correction subagent using `superpowers:receiving-code-review`, followed by a fresh Sol re-review.
- Allow at most two correction/re-review loops per review gate. If Critical or Important findings remain after two loops, stop and request user direction; record Minor findings for later.
- For the final Commit step, complete task verification, request a fresh Sol review of the accumulated task diff, resolve valid findings and re-review, update the plan checklists, and only then create the focused commit; no post-commit review is intended. A task is complete only after all steps are checked, its focused commit is created, and `git push origin main` succeeds.
- Work directly on `main`; do not add CI/CD or GitHub Actions before the full v1 acceptance gate passes.

---

## Planned File Structure

```text
.
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── src/yume_api/
│   │   │   ├── api/{routes.py,websocket.py}
│   │   │   ├── assets/{models.py,validator.py}
│   │   │   ├── config/{loader.py,models.py}
│   │   │   ├── contracts/{events.py,export.py}
│   │   │   ├── domain/{normalizer.py,reducer.py,room_policy.py}
│   │   │   ├── hermes/{client.py,models.py,sse.py}
│   │   │   ├── services/{session.py,world.py}
│   │   │   ├── main.py
│   │   │   └── settings.py
│   │   └── tests/
│   └── web/
│       ├── src/
│       │   ├── api/{client.ts,socket.ts}
│       │   ├── app/{App.tsx,app.css}
│       │   ├── game/{OfficeScene.ts,coordinates.ts,paths.ts,sprites.ts}
│       │   ├── store/world.ts
│       │   ├── ui/{AgentInspector.tsx,ChatPanel.tsx,ConnectionOverlay.tsx,Hud.tsx}
│       │   └── main.tsx
│       └── tests/
├── packages/contracts/
│   ├── schemas/world-event.schema.json
│   └── src/{index.ts,world-event.ts}
├── asset-packs/placeholder/
│   ├── atlases/
│   ├── maps/
│   ├── sources/
│   └── pack.json
├── config/dashboard.example.yaml
├── infra/docker/Dockerfile
├── tests/{e2e,fake_hermes}
├── compose.yaml
├── Makefile
├── package.json
├── pnpm-workspace.yaml
└── pyproject.toml
```

### Task 1: Initialize the Polyglot Monorepo

**Files:**
- Create: `.gitignore`
- Create: `.editorconfig`
- Create: `.nvmrc`
- Create: `.python-version`
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `pyproject.toml`
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/yume_api/main.py`
- Create: `apps/api/tests/test_health.py`
- Create: `apps/web/**` from the Vite React TypeScript template
- Create: `apps/web/src/app/App.test.tsx`
- Create: `Makefile`

**Interfaces:**
- Produces: `yume_api.main:create_app() -> FastAPI`
- Produces: root commands `make dev`, `make test`, `make lint`, and `make build`

- [x] **Step 1: Initialize Git and scaffold both applications**

Run:

```bash
git init -b main
git remote add origin https://github.com/nakanokazuha/ame-no-uzume.git
git ls-remote --heads origin
corepack enable
pnpm create vite apps/web --template react-ts
uv init --app --package apps/api --python 3.13
uv add --package yume-api fastapi httpx pydantic-settings uvicorn
uv add --package yume-api --dev ty pytest pytest-asyncio respx ruff
pnpm --dir apps/web add -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
pnpm add -Dw concurrently
```

Expected: a local `main` branch with the supplied `origin`, plus React TypeScript and Python applications. The remote-head check should return no refs for an empty repository; if it returns refs, fetch and reconcile them without force-pushing before continuing.

- [x] **Step 2: Add root workspace manifests**

Use these root settings:

```json
{
  "name": "ame-no-uzume",
  "private": true,
  "packageManager": "pnpm@10",
  "scripts": {
    "dev:web": "pnpm --dir apps/web dev",
    "build": "pnpm -r build",
    "lint": "pnpm -r lint",
    "test": "pnpm -r test",
    "typecheck": "pnpm -r typecheck"
  }
}
```

Set the web package name to `@yume/web` and add:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "lint": "eslint .",
    "typecheck": "tsc -b --noEmit"
  },
  "devDependencies": {
    "jsdom": "^26.0.0"
  }
}
```

Configure Vitest with `environment: "jsdom"` and a setup file importing `@testing-library/jest-dom/vitest`.

```yaml
packages:
  - apps/web
  - packages/contracts
```

```toml
[project]
name = "ame-no-uzume-workspace"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = []

[tool.uv]
package = false

[tool.uv.workspace]
members = ["apps/api"]
```

- [x] **Step 3: Write the failing backend health test**

```python
from fastapi.testclient import TestClient

from yume_api.main import create_app


def test_health_returns_ok() -> None:
    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [x] **Step 4: Run the backend test and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/test_health.py -q`

Expected: FAIL because `create_app` or `/api/health` does not exist.

- [x] **Step 5: Implement the minimal FastAPI application**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Ame-no-Uzume")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [x] **Step 6: Replace the Vite demo with a failing application-shell test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the office canvas and task control", () => {
    render(<App />);
    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Task Yume" })).toBeInTheDocument();
  });
});
```

Run: `pnpm --dir apps/web test --run`

Expected: FAIL because the shell has not been implemented.

- [x] **Step 7: Implement the minimal React shell**

```tsx
export function App() {
  return (
    <main>
      <div data-testid="office-canvas" />
      <button type="button">Task Yume</button>
    </main>
  );
}
```

- [x] **Step 8: Add root orchestration commands**

```make
.PHONY: dev test lint build

dev:
	pnpm exec concurrently --kill-others \
		"uv run --package yume-api uvicorn yume_api.main:app --reload --port 8000" \
		"pnpm --dir apps/web dev"

test:
	uv run --package yume-api pytest
	pnpm test

lint:
	uv run --package yume-api ruff check apps/api
	uv run --package yume-api ty check apps/api/src
	pnpm lint
	pnpm typecheck

build:
	pnpm build
	uv build --package yume-api
```

- [x] **Step 9: Verify the foundation**

Run: `make test && make lint && make build`

Expected: all commands exit 0.

- [x] **Step 10: Commit**

```bash
git add .gitignore .editorconfig .nvmrc .python-version AGENTS.md docs package.json pnpm-workspace.yaml pnpm-lock.yaml pyproject.toml uv.lock apps Makefile
git commit -m "chore: initialize dashboard monorepo"
git push -u origin main
```

### Task 2: Define and Generate the Domain Event Contract

**Files:**
- Create: `apps/api/src/yume_api/contracts/events.py`
- Create: `apps/api/src/yume_api/contracts/export.py`
- Create: `apps/api/tests/contracts/test_events.py`
- Create: `packages/contracts/package.json`
- Create: `packages/contracts/tsconfig.json`
- Create: `packages/contracts/schemas/world-event.schema.json`
- Create: `packages/contracts/src/world-event.ts`
- Create: `packages/contracts/src/index.ts`

**Interfaces:**
- Produces: `WorldEvent`, `WorldSnapshot`, `ConversationMessage`, `AgentView`, `RoomId`, `EvidenceLevel`
- Produces: `python -m yume_api.contracts.export`
- Produces: `@yume/contracts`

- [x] **Step 1: Write contract validation tests**

```python
from pydantic import TypeAdapter

from yume_api.contracts.events import AgentSpawnedEvent, WorldEvent


def test_agent_spawned_event_is_discriminated() -> None:
    event = TypeAdapter(WorldEvent).validate_python(
        {
            "schema_version": 1,
            "event_id": "evt-1",
            "sequence": 1,
            "occurred_at": "2026-07-27T00:00:00Z",
            "source": "hermes.session_stream",
            "evidence": "verified",
            "type": "agent.spawned",
            "agent_id": "delegated:run-1:call-1",
            "payload": {
                "kind": "delegated",
                "display_name": "Delegated Worker",
                "status": "entering",
                "room": "lobby"
            }
        }
    )

    assert isinstance(event, AgentSpawnedEvent)
    assert event.payload.room == "lobby"
```

- [x] **Step 2: Run the contract test and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/contracts/test_events.py -q`

Expected: FAIL because the event models do not exist.

- [x] **Step 3: Implement the complete v1 event types**

```python
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

EvidenceLevel = Literal["verified", "inferred"]
AgentKind = Literal["yume", "scheduled", "delegated"]
AgentStatus = Literal[
    "idle", "entering", "thinking", "moving", "working",
    "waiting_approval", "completed", "failed", "exiting", "stale"
]
RoomId = Literal["ceo", "memory", "research", "work", "automation", "lobby"]
ConnectionStatus = Literal["starting", "connected", "degraded", "disconnected"]


class AgentView(BaseModel):
    agent_id: str
    kind: AgentKind
    display_name: str
    status: AgentStatus
    room: RoomId
    evidence: EvidenceLevel
    task_summary: str | None = None
    started_at: datetime | None = None
    next_run_at: datetime | None = None


class ConversationMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    text: str


class WorldSnapshot(BaseModel):
    sequence: int
    connection: ConnectionStatus
    telemetry_mode: Literal["standard", "enhanced"] = "standard"
    session_id: str | None = None
    agents: list[AgentView]
    conversation: list[ConversationMessage] = Field(default_factory=list)


class EventBase(BaseModel):
    schema_version: Literal[1] = 1
    event_id: str
    sequence: int
    occurred_at: datetime
    source: str
    evidence: EvidenceLevel


class AgentSpawnedPayload(BaseModel):
    kind: AgentKind
    display_name: str
    status: AgentStatus
    room: RoomId
    task_summary: str | None = None
    started_at: datetime | None = None
    next_run_at: datetime | None = None


class AgentSpawnedEvent(EventBase):
    type: Literal["agent.spawned"]
    agent_id: str
    payload: AgentSpawnedPayload


class AgentStatePayload(BaseModel):
    status: AgentStatus
    room: RoomId
    task_summary: str | None = None
    next_run_at: datetime | None = None


class AgentStateChangedEvent(EventBase):
    type: Literal["agent.state_changed"]
    agent_id: str
    payload: AgentStatePayload


class AgentRemovedEvent(EventBase):
    type: Literal["agent.removed"]
    agent_id: str
    payload: dict[str, str] = Field(default_factory=dict)


class ConnectionPayload(BaseModel):
    status: ConnectionStatus
    reason: str | None = None


class ConnectionChangedEvent(EventBase):
    type: Literal["connection.changed"]
    payload: ConnectionPayload


class SnapshotPayload(BaseModel):
    snapshot: WorldSnapshot


class SnapshotReplacedEvent(EventBase):
    type: Literal["snapshot.replaced"]
    payload: SnapshotPayload


class ConversationPayload(BaseModel):
    text: str
    message_id: str


class ConversationDeltaEvent(EventBase):
    type: Literal["conversation.delta"]
    payload: ConversationPayload


class ConversationUserAddedEvent(EventBase):
    type: Literal["conversation.user_added"]
    payload: ConversationPayload


class ConversationCompletedEvent(EventBase):
    type: Literal["conversation.completed"]
    payload: ConversationPayload


class ApprovalPayload(BaseModel):
    run_id: str
    approval_id: str
    prompt: str


class ApprovalRequestedEvent(EventBase):
    type: Literal["approval.requested"]
    agent_id: str
    payload: ApprovalPayload


class ApprovalResolvedEvent(EventBase):
    type: Literal["approval.resolved"]
    agent_id: str
    payload: dict[str, str]


class RunFinishedPayload(BaseModel):
    run_id: str
    outcome: Literal["completed", "failed", "cancelled"]
    error: str | None = None


class RunFinishedEvent(EventBase):
    type: Literal["run.finished"]
    payload: RunFinishedPayload


WorldEvent = Annotated[
    AgentSpawnedEvent
    | AgentStateChangedEvent
    | AgentRemovedEvent
    | ConnectionChangedEvent
    | SnapshotReplacedEvent
    | ConversationUserAddedEvent
    | ConversationDeltaEvent
    | ConversationCompletedEvent
    | ApprovalRequestedEvent
    | ApprovalResolvedEvent
    | RunFinishedEvent,
    Field(discriminator="type"),
]
```

- [x] **Step 4: Export JSON Schema and generate TypeScript**

```python
import json
from pathlib import Path

from pydantic import TypeAdapter

from yume_api.contracts.events import WorldEvent


def main() -> None:
    output = Path("packages/contracts/schemas/world-event.schema.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(TypeAdapter(WorldEvent).json_schema(), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
```

Use this package script:

```json
{
  "name": "@yume/contracts",
  "private": true,
  "type": "module",
  "exports": {
    ".": "./src/index.ts"
  },
  "scripts": {
    "generate": "json2ts -i schemas/world-event.schema.json -o src/world-event.ts",
    "build": "tsc -p tsconfig.json",
    "test": "vitest run --passWithNoTests",
    "lint": "eslint src",
    "typecheck": "tsc -p tsconfig.json --noEmit"
  }
}
```

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "declaration": true,
    "emitDeclarationOnly": true,
    "outDir": "dist",
    "strict": true
  },
  "include": ["src"]
}
```

Run:

```bash
pnpm --dir packages/contracts add -D json-schema-to-typescript typescript vitest eslint
uv run --package yume-api python -m yume_api.contracts.export
pnpm --dir packages/contracts generate
```

- [x] **Step 5: Verify Python and TypeScript contracts**

Run:

```bash
uv run --package yume-api pytest apps/api/tests/contracts/test_events.py -q
pnpm --dir packages/contracts typecheck
```

Expected: both pass.

- [x] **Step 6: Commit**

```bash
git add apps/api/src/yume_api/contracts apps/api/tests/contracts packages/contracts
git commit -m "feat: define dashboard event contracts"
```

### Task 3: Validate Configuration and Build the Placeholder Asset Pack

**Files:**
- Create: `apps/api/src/yume_api/config/models.py`
- Create: `apps/api/src/yume_api/config/loader.py`
- Create: `apps/api/src/yume_api/assets/models.py`
- Create: `apps/api/src/yume_api/assets/validator.py`
- Create: `apps/api/tests/assets/test_validator.py`
- Create: `config/dashboard.example.yaml`
- Create: `asset-packs/placeholder/pack.json`
- Create: `asset-packs/placeholder/maps/office.json`
- Create: `asset-packs/placeholder/atlases/characters.json`
- Create: `tools/generate-placeholder-assets.mjs`

**Interfaces:**
- Produces: `load_dashboard_config(path: Path) -> DashboardConfig`
- Produces: `validate_asset_pack(root: Path, manifest: PackManifest) -> None`
- Produces: six semantic anchors and a walkable isometric map

- [x] **Step 1: Write failing validation tests**

```python
from pathlib import Path

import pytest

from yume_api.assets.validator import AssetPackError, load_and_validate_pack


def test_placeholder_pack_is_valid() -> None:
    manifest = load_and_validate_pack(Path("asset-packs/placeholder"))
    assert manifest.tile.width == 64
    assert set(manifest.anchors) == {
        "ceo", "memory", "research", "work", "automation", "lobby"
    }


def test_missing_atlas_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "pack.json").write_text(
        '{"schema_version":1,"id":"test","name":"Test",'
        '"tile":{"width":64,"height":32},'
        '"character":{"width":32,"height":48},'
        '"map":"maps/office.json","atlas":"atlases/missing.json",'
        '"anchors":{},"animations":{}}',
        encoding="utf-8",
    )

    with pytest.raises(AssetPackError, match="atlases/missing.json"):
        load_and_validate_pack(tmp_path)
```

- [x] **Step 2: Run validation tests and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/assets/test_validator.py -q`

Expected: FAIL because the pack models and validator do not exist.

- [x] **Step 3: Implement manifest and dashboard models**

```python
from typing import Literal

from pydantic import BaseModel, Field


class Size(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Anchor(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class UiManifest(BaseModel):
    image: str
    atlas: str
    nine_slice: dict[str, tuple[int, int, int, int]] = Field(default_factory=dict)


class PackManifest(BaseModel):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    tile: Size
    character: Size
    map: str
    atlas: str
    anchors: dict[str, Anchor]
    animations: dict[str, list[int]]
    ui: UiManifest | None = None
```

```python
from pydantic import BaseModel, Field


class RoomRule(BaseModel):
    pattern: str
    room: str


class DashboardConfig(BaseModel):
    asset_pack: str = "placeholder"
    hermes_base_url: str = "http://127.0.0.1:8642"
    data_dir: str = "/data"
    room_rules: list[RoomRule] = Field(default_factory=list)
```

- [x] **Step 4: Implement strict file and semantic validation**

```python
import json
from pathlib import Path

from yume_api.assets.models import PackManifest

REQUIRED_ANCHORS = {"ceo", "memory", "research", "work", "automation", "lobby"}


class AssetPackError(ValueError):
    pass


def load_and_validate_pack(root: Path) -> PackManifest:
    manifest_path = root / "pack.json"
    manifest = PackManifest.model_validate_json(manifest_path.read_text("utf-8"))
    for relative in (manifest.map, manifest.atlas):
        if not (root / relative).is_file():
            raise AssetPackError(f"missing asset: {relative}")
    missing = REQUIRED_ANCHORS - set(manifest.anchors)
    if missing:
        raise AssetPackError(f"missing semantic anchors: {sorted(missing)}")
    map_data = json.loads((root / manifest.map).read_text("utf-8"))
    if map_data.get("orientation") != "isometric":
        raise AssetPackError("map orientation must be isometric")
    return manifest
```

The implementation must also fulfill the approved asset-pack contract: reject
absolute and escaping paths; validate 64×32 tiles and 32×48 character canvases;
validate tileset and atlas PNG paths, dimensions, and atlas frame bounds; require
the listed animation aliases and their referenced frames; and require complete
Tiled layers with walkable, mutually reachable semantic anchors. Convert expected
manifest, JSON, and file failures to `AssetPackError` so startup diagnostics can
report invalid packs without crashing.

- [x] **Step 5: Create the production-shaped placeholder manifest**

```json
{
  "schema_version": 1,
  "id": "placeholder",
  "name": "Yume Placeholder Office",
  "tile": {"width": 64, "height": 32},
  "character": {"width": 32, "height": 48},
  "map": "maps/office.json",
  "atlas": "atlases/characters.json",
  "anchors": {
    "ceo": {"x": 2, "y": 7},
    "memory": {"x": 3, "y": 3},
    "lobby": {"x": 8, "y": 3},
    "research": {"x": 9, "y": 7},
    "work": {"x": 3, "y": 10},
    "automation": {"x": 8, "y": 10}
  },
  "animations": {
    "yume-idle-sw": [0, 1],
    "yume-walk-sw": [14, 15, 16, 17],
    "yume-think-sw": [18, 19, 20, 21],
    "yume-work-sw": [22, 23, 24, 25],
    "yume-waiting-sw": [18, 19],
    "yume-success-sw": [26, 27, 28],
    "yume-failed-sw": [29, 30],
    "scheduled-idle-sw": [0, 1],
    "scheduled-walk-sw": [14, 15, 16, 17],
    "scheduled-work-sw": [22, 23, 24, 25],
    "scheduled-waiting-sw": [18, 19],
    "scheduled-failed-sw": [29, 30],
    "worker-idle-sw": [0, 1],
    "worker-walk-sw": [14, 15, 16, 17],
    "worker-work-sw": [22, 23, 24, 25],
    "worker-enter-sw": [14, 15, 16, 17],
    "worker-exit-sw": [14, 15, 16, 17],
    "worker-report-sw": [26, 27, 28],
    "worker-waiting-sw": [18, 19],
    "worker-failed-sw": [29, 30]
  }
}
```

- [x] **Step 6: Generate deterministic placeholder PNGs**

Add `pngjs` to the root dev dependencies and implement:

```js
import { mkdirSync, writeFileSync } from "node:fs";
import { PNG } from "pngjs";

function image(width, height, paint) {
  const png = new PNG({ width, height });
  paint(png);
  return PNG.sync.write(png);
}

function setPixel(png, x, y, [r, g, b, a = 255]) {
  const offset = (png.width * y + x) << 2;
  [png.data[offset], png.data[offset + 1], png.data[offset + 2], png.data[offset + 3]] =
    [r, g, b, a];
}

mkdirSync("asset-packs/placeholder/tiles", { recursive: true });
mkdirSync("asset-packs/placeholder/atlases", { recursive: true });

writeFileSync(
  "asset-packs/placeholder/tiles/office.png",
  image(64, 32, (png) => {
    for (let y = 0; y < 32; y += 1) {
      const half = y < 16 ? y * 2 : (31 - y) * 2;
      for (let x = 31 - half; x <= 32 + half; x += 1) {
        setPixel(png, x, y, [92, 118, 126, 255]);
      }
    }
  }),
);

writeFileSync(
  "asset-packs/placeholder/atlases/characters.png",
  image(32 * 31, 48, (png) => {
    for (let frame = 0; frame < 31; frame += 1) {
      for (let y = 12; y < 44; y += 1) {
        for (let x = frame * 32 + 10; x < frame * 32 + 22; x += 1) {
          setPixel(png, x, y, frame < 2 ? [238, 196, 84, 255] : [94, 166, 206, 255]);
        }
      }
    }
  }),
);

const frames = Object.fromEntries(
  Array.from({ length: 31 }, (_, frame) => [
    `frame-${frame}`,
    {
      frame: { x: frame * 32, y: 0, w: 32, h: 48 },
      rotated: false,
      trimmed: false,
      spriteSourceSize: { x: 0, y: 0, w: 32, h: 48 },
      sourceSize: { w: 32, h: 48 },
    },
  ]),
);
writeFileSync(
  "asset-packs/placeholder/atlases/characters.json",
  `${JSON.stringify({ frames, meta: { image: "characters.png", scale: "1" } }, null, 2)}\n`,
);

mkdirSync("asset-packs/placeholder/maps", { recursive: true });
const width = 12;
const height = 12;
const layer = (id, name, data) => ({
  id, name, type: "tilelayer", width, height, x: 0, y: 0, data,
});
writeFileSync(
  "asset-packs/placeholder/maps/office.json",
  `${JSON.stringify({
    compressionlevel: -1,
    height,
    infinite: false,
    layers: [
      layer(1, "floor", Array(width * height).fill(1)),
      layer(2, "walls", Array(width * height).fill(0)),
      layer(3, "furniture-low", Array(width * height).fill(0)),
      layer(4, "furniture-high", Array(width * height).fill(0)),
    ],
    nextlayerid: 5,
    nextobjectid: 1,
    orientation: "isometric",
    renderorder: "right-down",
    tileheight: 32,
    tilesets: [{
      firstgid: 1,
      columns: 1,
      image: "../tiles/office.png",
      imageheight: 32,
      imagewidth: 64,
      name: "office",
      tilecount: 1,
      tileheight: 32,
      tilewidth: 64,
    }],
    tilewidth: 64,
    type: "map",
    version: "1.10",
    width,
  }, null, 2)}\n`,
);
```

Run: `node tools/generate-placeholder-assets.mjs`

- [x] **Step 7: Verify the placeholder pack**

Run:

```bash
uv run --package yume-api pytest apps/api/tests/assets/test_validator.py -q
node tools/generate-placeholder-assets.mjs
git diff --exit-code asset-packs/placeholder
```

Expected: tests pass and regeneration produces no diff.

- [x] **Step 8: Commit**

```bash
git add apps/api/src/yume_api/config apps/api/src/yume_api/assets apps/api/tests/assets config asset-packs/placeholder tools package.json pnpm-lock.yaml
git commit -m "feat: add validated placeholder asset pack"
```

### Task 4: Implement the Hermes HTTP Client and Persistent Session

**Files:**
- Create: `apps/api/src/yume_api/hermes/models.py`
- Create: `apps/api/src/yume_api/hermes/client.py`
- Create: `apps/api/src/yume_api/hermes/sse.py`
- Create: `apps/api/src/yume_api/services/session.py`
- Create: `apps/api/tests/hermes/test_client.py`
- Create: `apps/api/tests/services/test_session.py`

**Interfaces:**
- Produces: `HermesClient.get_capabilities() -> HermesCapabilities`
- Produces: `HermesClient.stream_task(capabilities, session_id, text, history) -> AsyncIterator[HermesStreamEvent]`
- Produces: `HermesClient.get_session_messages(session_id) -> list[ConversationMessage]`
- Produces: `SessionService.ensure_session() -> str`
- Produces: `SessionService.reset_session() -> str`

- [ ] **Step 1: Write failing client and session tests**

```python
import pytest
import respx
from httpx import Response

from yume_api.hermes.client import HermesClient


@pytest.mark.asyncio
@respx.mock
async def test_capabilities_are_discovered() -> None:
    respx.get("http://hermes/v1/capabilities").mock(
        return_value=Response(
            200,
            json={"features": {"session_chat_stream": True, "run_stop": True}},
        )
    )
    client = HermesClient("http://hermes", "secret")

    capabilities = await client.get_capabilities()

    assert capabilities.session_chat_stream is True
    assert capabilities.run_stop is True
```

```python
@pytest.mark.asyncio
async def test_ensure_session_reuses_persisted_id(tmp_path, fake_client) -> None:
    service = SessionService(fake_client, tmp_path / "state.json")
    fake_client.create_session.return_value = "session-1"

    first = await service.ensure_session()
    second = await service.ensure_session()

    assert first == second == "session-1"
    fake_client.create_session.assert_awaited_once_with("Yume Dashboard")
```

```python
@pytest.mark.asyncio
async def test_task_falls_back_to_runs_when_session_stream_is_absent(fake_client) -> None:
    capabilities = HermesCapabilities(
        run_submission=True, run_status=True, run_events_sse=True
    )
    fake_client.create_run.return_value = "run-1"

    events = [
        event
        async for event in fake_client.stream_task(
            capabilities,
            "session-1",
            "Research hooks",
            [ConversationMessage(message_id="m1", role="assistant", text="Ready")],
        )
    ]

    fake_client.create_run.assert_awaited_once()
    assert events[-1].event == "run.completed"
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/hermes apps/api/tests/services/test_session.py -q`

Expected: FAIL because the client and session service do not exist.

- [ ] **Step 3: Implement capability and session models**

```python
from typing import Literal

from pydantic import BaseModel


class HermesCapabilities(BaseModel):
    session_chat_stream: bool = False
    run_submission: bool = False
    run_status: bool = False
    run_events_sse: bool = False
    run_stop: bool = False
    run_approval: bool = False


class HermesStreamEvent(BaseModel):
    event: str
    data: dict


class HermesRun(BaseModel):
    run_id: str
    status: Literal["started", "running", "waiting_approval", "stopping", "completed", "failed", "cancelled"]
    output: str | None = None
    error: str | None = None
```

- [ ] **Step 4: Implement authenticated HTTP calls and SSE parsing**

```python
from collections.abc import AsyncIterator

import httpx

from yume_api.hermes.models import HermesCapabilities, HermesStreamEvent
from yume_api.hermes.sse import iter_sse


class HermesClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(30, read=None),
        )

    async def get_capabilities(self) -> HermesCapabilities:
        response = await self._client.get("/v1/capabilities")
        response.raise_for_status()
        return HermesCapabilities.model_validate(response.json().get("features", {}))

    async def create_session(self, title: str) -> str:
        response = await self._client.post("/api/sessions", json={"title": title})
        response.raise_for_status()
        return str(response.json()["id"])

    async def stream_session_chat(
        self, session_id: str, text: str
    ) -> AsyncIterator[HermesStreamEvent]:
        async with self._client.stream(
            "POST",
            f"/api/sessions/{session_id}/chat/stream",
            json={"input": text},
        ) as response:
            response.raise_for_status()
            async for event in iter_sse(response.aiter_lines()):
                yield event

    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        response = await self._client.get(f"/api/sessions/{session_id}/messages")
        response.raise_for_status()
        return [
            ConversationMessage(
                message_id=str(item["id"]),
                role=item["role"],
                text=extract_text(item["content"]),
            )
            for item in response.json()
            if item.get("role") in {"user", "assistant"}
        ]

    async def stream_task(
        self,
        capabilities: HermesCapabilities,
        session_id: str,
        text: str,
        history: list[ConversationMessage],
    ) -> AsyncIterator[HermesStreamEvent]:
        if capabilities.session_chat_stream:
            async for event in self.stream_session_chat(session_id, text):
                yield event
            return
        if not capabilities.run_submission or not capabilities.run_status:
            raise RuntimeError("Hermes exposes neither session streaming nor compatible runs")
        run_id = await self.create_run(session_id, text, history)
        if capabilities.run_events_sse:
            async for event in self.stream_run_events(run_id):
                yield event
            return
        while True:
            status = await self.get_run(run_id)
            if status.status in {"completed", "failed", "cancelled"}:
                yield run_status_to_event(status)
                return
            await asyncio.sleep(1)
```

`create_run` sends `POST /v1/runs` with `input`, `session_id`, and serialized `conversation_history`. `stream_run_events` reads `GET /v1/runs/{run_id}/events`; `get_run` polls `GET /v1/runs/{run_id}`. Unit tests cover SSE and polling fallback, and assert that bearer tokens never appear in exceptions or captured logs.

```python
async def create_run(
    self, session_id: str, text: str, history: list[ConversationMessage]
) -> str:
    response = await self._client.post(
        "/v1/runs",
        json={
            "input": text,
            "session_id": session_id,
            "conversation_history": [
                {"role": item.role, "content": item.text} for item in history
            ],
        },
    )
    response.raise_for_status()
    return str(response.json()["run_id"])

async def stream_run_events(self, run_id: str) -> AsyncIterator[HermesStreamEvent]:
    async with self._client.stream("GET", f"/v1/runs/{run_id}/events") as response:
        response.raise_for_status()
        async for event in iter_sse(response.aiter_lines()):
            yield event

async def get_run(self, run_id: str) -> HermesRun:
    response = await self._client.get(f"/v1/runs/{run_id}")
    response.raise_for_status()
    return HermesRun.model_validate(response.json())

def extract_text(content: str | list[dict]) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        str(part.get("text", ""))
        for part in content
        if part.get("type") in {"text", "output_text"}
    )

def run_status_to_event(run: HermesRun) -> HermesStreamEvent:
    name = "run.completed" if run.status == "completed" else "run.failed"
    return HermesStreamEvent(
        event=name,
        data={"run_id": run.run_id, "output": run.output, "error": run.error},
    )
```

```python
from collections.abc import AsyncIterator
import json

from yume_api.hermes.models import HermesStreamEvent


async def iter_sse(lines: AsyncIterator[str]) -> AsyncIterator[HermesStreamEvent]:
    event_name = "message"
    data_lines: list[str] = []
    async for line in lines:
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif not line and data_lines:
            yield HermesStreamEvent(
                event=event_name,
                data=json.loads("\n".join(data_lines)),
            )
            event_name, data_lines = "message", []
```

- [ ] **Step 5: Implement atomic session persistence**

```python
import json
import os
from pathlib import Path


class SessionService:
    def __init__(self, client, state_path: Path) -> None:
        self._client = client
        self._state_path = state_path
        self._session_id: str | None = None

    async def ensure_session(self) -> str:
        if self._session_id:
            return self._session_id
        if self._state_path.exists():
            self._session_id = json.loads(self._state_path.read_text("utf-8"))["session_id"]
            return self._session_id
        self._session_id = await self._client.create_session("Yume Dashboard")
        self._persist(self._session_id)
        return self._session_id

    async def reset_session(self) -> str:
        self._session_id = await self._client.create_session("Yume Dashboard")
        self._persist(self._session_id)
        return self._session_id

    def _persist(self, session_id: str) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"session_id": session_id}), "utf-8")
        os.replace(temporary, self._state_path)
```

- [ ] **Step 6: Verify all Hermes client tests**

Run: `uv run --package yume-api pytest apps/api/tests/hermes apps/api/tests/services/test_session.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/yume_api/hermes apps/api/src/yume_api/services/session.py apps/api/tests/hermes apps/api/tests/services/test_session.py
git commit -m "feat: connect persistent dashboard session to Hermes"
```

### Task 5: Normalize Hermes Activity and Reduce World State

**Files:**
- Create: `apps/api/src/yume_api/domain/room_policy.py`
- Create: `apps/api/src/yume_api/domain/normalizer.py`
- Create: `apps/api/src/yume_api/domain/reducer.py`
- Create: `apps/api/src/yume_api/contracts/factories.py`
- Create: `apps/api/tests/domain/test_room_policy.py`
- Create: `apps/api/tests/domain/test_normalizer.py`
- Create: `apps/api/tests/domain/test_reducer.py`

**Interfaces:**
- Produces: `RoomPolicy.resolve(tool_name: str) -> RoomId`
- Produces: `HermesNormalizer.normalize(event, context) -> list[WorldEvent]`
- Produces: `WorldReducer.apply(event: WorldEvent) -> WorldSnapshot`

- [ ] **Step 1: Write failing verified-first behavior tests**

```python
def test_unknown_tool_maps_to_work() -> None:
    policy = RoomPolicy([])
    assert policy.resolve("brand_new_tool") == "work"


def test_delegate_tool_spawns_generic_verified_worker() -> None:
    events = HermesNormalizer(RoomPolicy([])).normalize(
        HermesStreamEvent(
            event="tool.started",
            data={"run_id": "run-1", "tool_call_id": "call-2", "tool_name": "delegate_task"},
        ),
        sequence=5,
    )

    spawned = events[0]
    assert spawned.type == "agent.spawned"
    assert spawned.agent_id == "delegated:run-1:call-2"
    assert spawned.evidence == "verified"
    assert spawned.payload.display_name == "Delegated Worker"
    assert spawned.payload.room == "lobby"
    assert spawned.payload.task_summary is None
```

- [ ] **Step 2: Run domain tests and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/domain -q`

Expected: FAIL because policy, normalizer, and reducer do not exist.

- [ ] **Step 3: Implement ordered room rules**

```python
from fnmatch import fnmatch

from yume_api.contracts.events import RoomId


class RoomPolicy:
    DEFAULTS = [
        ("memory*", "memory"),
        ("web_*", "research"),
        ("browser*", "research"),
        ("terminal*", "work"),
        ("file*", "work"),
        ("cron*", "automation"),
    ]

    def __init__(self, rules: list[tuple[str, RoomId]]) -> None:
        self._rules = rules + self.DEFAULTS

    def resolve(self, tool_name: str) -> RoomId:
        for pattern, room in self._rules:
            if fnmatch(tool_name, pattern):
                return room
        return "work"
```

- [ ] **Step 4: Implement deterministic event normalization**

```python
from yume_api.contracts.events import WorldEvent
from yume_api.hermes.models import HermesStreamEvent


class HermesNormalizer:
    HANDLERS = {
        "assistant.delta": "_assistant_delta",
        "tool.started": "_tool_started",
        "tool.completed": "_tool_completed",
        "approval.requested": "_approval_requested",
        "run.completed": "_run_completed",
        "run.failed": "_run_failed",
    }

    def __init__(self, room_policy: RoomPolicy) -> None:
        self._rooms = room_policy

    def normalize(
        self, event: HermesStreamEvent, sequence: int
    ) -> list[WorldEvent]:
        handler_name = self.HANDLERS.get(event.event)
        if handler_name is None:
            return []
        return getattr(self, handler_name)(event.data, sequence)
```

Implement the handlers with these exact outputs:

```python
def _assistant_delta(self, data, sequence):
    return [make_conversation_delta(
        text=str(data.get("delta", "")),
        message_id=str(data["message_id"]),
        sequence=sequence,
    )]

def _tool_started(self, data, sequence):
    if data.get("tool_name") == "delegate_task":
        return [make_delegated_spawn(data, sequence)]
    return [make_agent_state(
        "yume", "working", self._rooms.resolve(str(data["tool_name"])),
        sequence, evidence="verified",
    )]

def _tool_completed(self, data, sequence):
    delegated_id = delegated_agent_id(data)
    if delegated_id is None:
        return [make_agent_state("yume", "thinking", "ceo", sequence)]
    return [
        make_agent_state(delegated_id, "completed", "work", sequence),
        make_agent_removed(delegated_id, sequence + 1),
    ]

def _approval_requested(self, data, sequence):
    agent_id = agent_id_from(data) or "yume"
    return [
        make_agent_state(agent_id, "waiting_approval", "work", sequence),
        make_approval_requested(data, agent_id, sequence + 1),
    ]

def _run_completed(self, data, sequence):
    return [
        make_conversation_completed(data, sequence),
        make_run_finished(data, "completed", sequence + 1),
        make_agent_state("yume", "idle", "ceo", sequence + 2),
    ]

def _run_failed(self, data, sequence):
    agent_id = agent_id_from(data)
    events = [make_run_finished(data, "failed", sequence)]
    if agent_id and agent_id != "yume":
        events.append(make_agent_state(agent_id, "failed", "work", sequence + 1))
    events.append(make_agent_state("yume", "idle", "ceo", sequence + len(events)))
    return events
```

```python
def delegated_agent_id(data: dict) -> str | None:
    run_id = data.get("run_id")
    call_id = data.get("tool_call_id")
    return f"delegated:{run_id}:{call_id}" if run_id and call_id else None

def agent_id_from(data: dict) -> str | None:
    return data.get("agent_id") or delegated_agent_id(data)

def make_delegated_spawn(data: dict, sequence: int) -> AgentSpawnedEvent:
    agent_id = delegated_agent_id(data)
    if agent_id is None:
        raise ValueError("delegation event requires run_id and tool_call_id")
    return make_agent_spawned(
        agent_id, "delegated", "Delegated Worker", "lobby", sequence,
        task_summary=data.get("task_summary"),
    )
```

The helper constructors assign timestamps and IDs, truncate user-visible summaries to 240 characters, and copy only declared contract fields. A missing summary remains `None`.

Implement the shared constructors in `contracts/factories.py`:

```python
def make_agent_state(
    agent_id: str,
    status: AgentStatus,
    room: RoomId,
    sequence: int,
    *,
    evidence: EvidenceLevel = "verified",
    task_summary: str | None = None,
    next_run_at: datetime | None = None,
) -> AgentStateChangedEvent:
    return AgentStateChangedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="hermes.session_stream", evidence=evidence,
        type="agent.state_changed", agent_id=agent_id,
        payload=AgentStatePayload(
            status=status, room=room,
            task_summary=task_summary[:240] if task_summary else None,
            next_run_at=next_run_at,
        ),
    )

def make_agent_removed(agent_id: str, sequence: int) -> AgentRemovedEvent:
    return AgentRemovedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="hermes.session_stream", evidence="verified",
        type="agent.removed", agent_id=agent_id, payload={},
    )

def make_user_message(text: str, sequence: int) -> ConversationUserAddedEvent:
    return ConversationUserAddedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="dashboard.user", evidence="verified", type="conversation.user_added",
        payload=ConversationPayload(text=text, message_id=str(uuid4())),
    )

def make_connection_changed(
    status: ConnectionStatus, reason: str | None, sequence: int
) -> ConnectionChangedEvent:
    return ConnectionChangedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="dashboard.adapter", evidence="verified", type="connection.changed",
        payload=ConnectionPayload(status=status, reason=reason),
    )
```

```python
def make_agent_spawned(
    agent_id: str, kind: AgentKind, display_name: str, room: RoomId,
    sequence: int, task_summary: str | None = None,
    status: AgentStatus = "entering",
    next_run_at: datetime | None = None,
) -> AgentSpawnedEvent:
    return AgentSpawnedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="hermes.session_stream", evidence="verified",
        type="agent.spawned", agent_id=agent_id,
        payload=AgentSpawnedPayload(
            kind=kind, display_name=display_name, status=status, room=room,
            task_summary=task_summary[:240] if task_summary else None,
            started_at=datetime.now(UTC), next_run_at=next_run_at,
        ),
    )

def make_conversation_delta(
    text: str, message_id: str, sequence: int
) -> ConversationDeltaEvent:
    return ConversationDeltaEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="hermes.session_stream", evidence="verified",
        type="conversation.delta",
        payload=ConversationPayload(text=text, message_id=message_id),
    )

def make_conversation_completed(data: dict, sequence: int) -> ConversationCompletedEvent:
    return ConversationCompletedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="hermes.session_stream", evidence="verified",
        type="conversation.completed",
        payload=ConversationPayload(
            text=str(data.get("output", "")),
            message_id=str(data.get("message_id", data["run_id"])),
        ),
    )

def make_approval_requested(
    data: dict, agent_id: str, sequence: int
) -> ApprovalRequestedEvent:
    return ApprovalRequestedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="hermes.session_stream", evidence="verified",
        type="approval.requested", agent_id=agent_id,
        payload=ApprovalPayload(
            run_id=str(data["run_id"]), approval_id=str(data["approval_id"]),
            prompt=str(data.get("prompt", "Approval required"))[:240],
        ),
    )

def make_run_finished(
    data: dict, outcome: Literal["completed", "failed", "cancelled"], sequence: int
) -> RunFinishedEvent:
    return RunFinishedEvent(
        event_id=str(uuid4()), sequence=sequence, occurred_at=datetime.now(UTC),
        source="hermes.session_stream", evidence="verified", type="run.finished",
        payload=RunFinishedPayload(
            run_id=str(data["run_id"]), outcome=outcome,
            error=str(data["error"])[:240] if data.get("error") else None,
        ),
    )

def make_snapshot_event(snapshot: WorldSnapshot) -> SnapshotReplacedEvent:
    return SnapshotReplacedEvent(
        event_id=str(uuid4()), sequence=snapshot.sequence,
        occurred_at=datetime.now(UTC), source="dashboard.snapshot",
        evidence="verified", type="snapshot.replaced",
        payload=SnapshotPayload(snapshot=snapshot),
    )
```

```python
@pytest.mark.parametrize(
    "event",
    [
        make_agent_state("yume", "idle", "ceo", 1),
        make_agent_removed("delegated:1", 2),
        make_user_message("hello", 3),
        make_connection_changed("connected", None, 4),
        make_agent_spawned("delegated:1", "delegated", "Worker", "lobby", 5),
        make_conversation_delta("hi", "message-1", 6),
        make_conversation_completed({"run_id": "run-1", "output": "done"}, 7),
        make_approval_requested(
            {"run_id": "run-1", "approval_id": "approval-1"}, "yume", 8
        ),
        make_run_finished({"run_id": "run-1"}, "completed", 9),
        make_snapshot_event(WorldReducer().snapshot),
    ],
)
def test_event_factory_output_validates(event: WorldEvent) -> None:
    assert TypeAdapter(WorldEvent).validate_python(event.model_dump()) == event
```

- [ ] **Step 5: Implement the authoritative reducer**

```python
from yume_api.contracts.events import AgentView, WorldSnapshot


class WorldReducer:
    def __init__(self) -> None:
        self.snapshot = WorldSnapshot(
            sequence=0,
            connection="starting",
            agents=[
                AgentView(
                    agent_id="yume",
                    kind="yume",
                    display_name="Yume",
                    status="idle",
                    room="ceo",
                    evidence="verified",
                )
            ],
        )

    def apply(self, event):
        agents = {agent.agent_id: agent for agent in self.snapshot.agents}
        if event.type == "agent.spawned":
            agents[event.agent_id] = AgentView(
                agent_id=event.agent_id,
                evidence=event.evidence,
                **event.payload.model_dump(),
            )
        elif event.type == "agent.state_changed" and event.agent_id in agents:
            agents[event.agent_id] = agents[event.agent_id].model_copy(
                update=event.payload.model_dump(exclude_none=True)
            )
        elif event.type == "agent.removed":
            agents.pop(event.agent_id, None)
        elif event.type == "connection.changed":
            self.snapshot.connection = event.payload.status
        elif event.type == "conversation.user_added":
            self.snapshot.conversation.append(ConversationMessage(
                message_id=event.payload.message_id,
                role="user",
                text=event.payload.text,
            ))
        elif event.type == "conversation.completed":
            self.snapshot.conversation.append(ConversationMessage(
                message_id=event.payload.message_id,
                role="assistant",
                text=event.payload.text,
            ))
        elif event.type == "snapshot.replaced":
            self.snapshot = event.payload.snapshot.model_copy(deep=True)
            return self.snapshot.model_copy(deep=True)
        self.snapshot.sequence = event.sequence
        self.snapshot.agents = list(agents.values())
        return self.snapshot.model_copy(deep=True)
```

- [ ] **Step 6: Run all domain tests**

Run: `uv run --package yume-api pytest apps/api/tests/domain -q`

Expected: PASS, including delegation, approval, completion, failure, and unknown-tool cases.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/yume_api/domain apps/api/tests/domain
git commit -m "feat: normalize Hermes activity into world state"
```

### Task 6: Expose the World Service, Commands, and WebSocket

**Files:**
- Create: `apps/api/src/yume_api/services/world.py`
- Create: `apps/api/src/yume_api/api/routes.py`
- Create: `apps/api/src/yume_api/api/websocket.py`
- Modify: `apps/api/src/yume_api/main.py`
- Create: `apps/api/tests/api/test_world_api.py`
- Create: `apps/api/tests/api/test_websocket.py`

**Interfaces:**
- Produces: `WorldService.snapshot() -> WorldSnapshot`
- Produces: `WorldService.submit_task(text: str) -> str`
- Produces: REST `/api/bootstrap`, `/api/tasks`, `/api/session/reset`
- Produces: WebSocket `/api/events`

- [ ] **Step 1: Write failing API and WebSocket tests**

```python
def test_bootstrap_returns_snapshot(client) -> None:
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    assert response.json()["world"]["agents"][0]["agent_id"] == "yume"
    assert response.json()["asset_pack"]["id"] == "placeholder"


def test_task_rejects_blank_input(client) -> None:
    response = client.post("/api/tasks", json={"text": "   "})
    assert response.status_code == 422
```

```python
def test_websocket_sends_snapshot_first(client) -> None:
    with client.websocket_connect("/api/events") as socket:
        event = socket.receive_json()
    assert event["type"] == "snapshot.replaced"
    assert event["payload"]["snapshot"]["agents"][0]["agent_id"] == "yume"
```

- [ ] **Step 2: Run API tests and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/api -q`

Expected: FAIL because the service and routes do not exist.

- [ ] **Step 3: Implement the world service and bounded subscribers**

```python
import asyncio
from collections.abc import AsyncIterator


class WorldService:
    def __init__(self, session, client, normalizer, reducer) -> None:
        self._session = session
        self._client = client
        self._normalizer = normalizer
        self._reducer = reducer
        self._subscribers: set[asyncio.Queue] = set()
        self._task_lock = asyncio.Lock()

    def snapshot(self):
        return self._reducer.snapshot.model_copy(deep=True)

    async def subscribe(self) -> AsyncIterator:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event) -> None:
        self._reducer.apply(event)
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def submit_task(self, text: str) -> str:
        if self._task_lock.locked():
            raise RuntimeError("a task is already running")
        session_id = await self._session.ensure_session()
        async with self._task_lock:
            history = self._reducer.snapshot.conversation
            await self.publish(make_user_message(text, self._reducer.snapshot.sequence + 1))
            async for raw in self._client.stream_task(
                self._capabilities, session_id, text, history
            ):
                for event in self._normalizer.normalize(
                    raw, self._reducer.snapshot.sequence + 1
                ):
                    await self.publish(event)
    return session_id
```

At application startup, call `ensure_session`, then `get_session_messages`, and seed `snapshot.session_id` and `snapshot.conversation` before accepting browser connections. If the persisted session returns 404, create exactly one replacement session, persist it atomically, and start with an empty conversation.

- [ ] **Step 4: Implement REST and WebSocket routes**

```python
from pydantic import BaseModel, Field


class BootstrapResponse(BaseModel):
    world: WorldSnapshot
    asset_pack: PackManifest


class TaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


@router.get("/bootstrap")
async def bootstrap(request: Request):
    return BootstrapResponse(
        world=request.app.state.world.snapshot(),
        asset_pack=request.app.state.asset_pack,
    )


@router.post("/tasks", status_code=202)
async def submit_task(body: TaskRequest, request: Request):
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "task text cannot be blank")
    asyncio.create_task(request.app.state.world.submit_task(text))
    return {"status": "accepted"}
```

```python
@router.websocket("/events")
async def events(websocket: WebSocket) -> None:
    await websocket.accept()
    world = websocket.app.state.world
    await websocket.send_json(make_snapshot_event(world.snapshot()).model_dump(mode="json"))
    async for event in world.subscribe():
        await websocket.send_json(event.model_dump(mode="json"))
```

- [ ] **Step 5: Add capability-gated reset, stop, and approval routes**

```python
class ApprovalDecision(BaseModel):
    approval_id: str
    approved: bool


@router.post("/session/reset")
async def reset_session(request: Request):
    session_id = await request.app.state.world.reset_session()
    return {"session_id": session_id}


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str, request: Request):
    if not request.app.state.capabilities.run_stop:
        raise HTTPException(501, "Hermes run stop is unavailable")
    await request.app.state.hermes.stop_run(run_id)
    return {"status": "stopped"}


@router.post("/runs/{run_id}/approval")
async def resolve_approval(run_id: str, body: ApprovalDecision, request: Request):
    if not request.app.state.capabilities.run_approval:
        raise HTTPException(501, "Hermes run approval is unavailable")
    await request.app.state.hermes.resolve_approval(
        run_id, body.approval_id, body.approved
    )
    return {"status": "resolved"}
```

Tests must assert both supported and unsupported capability paths.

- [ ] **Step 6: Verify API behavior**

Run: `uv run --package yume-api pytest apps/api/tests/api -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/yume_api/services/world.py apps/api/src/yume_api/api apps/api/src/yume_api/main.py apps/api/tests/api
git commit -m "feat: expose task and world event API"
```

### Task 7: Discover Scheduled Jobs as Persistent Workers

**Files:**
- Modify: `apps/api/src/yume_api/hermes/client.py`
- Create: `apps/api/src/yume_api/services/jobs.py`
- Modify: `apps/api/src/yume_api/services/world.py`
- Create: `apps/api/tests/services/test_jobs.py`

**Interfaces:**
- Produces: `HermesClient.list_jobs() -> list[HermesJob]`
- Produces: `JobSynchronizer.reconcile(jobs, snapshot) -> list[WorldEvent]`

- [ ] **Step 1: Write a failing scheduled-worker reconciliation test**

```python
def test_job_becomes_persistent_automation_worker() -> None:
    events = JobSynchronizer().reconcile(
        [HermesJob(id="daily-memory", name="Daily memory", next_run_at="2026-07-28T00:00:00Z")],
        WorldReducer().snapshot,
        sequence=1,
    )

    assert events[0].agent_id == "scheduled:daily-memory"
    assert events[0].payload.kind == "scheduled"
    assert events[0].payload.room == "automation"
```

- [ ] **Step 2: Run the test and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/services/test_jobs.py -q`

Expected: FAIL because job discovery is missing.

- [ ] **Step 3: Implement job discovery and reconciliation**

```python
class HermesJob(BaseModel):
    id: str
    name: str
    next_run_at: datetime | None = None


async def list_jobs(self) -> list[HermesJob]:
    response = await self._client.get("/api/jobs")
    response.raise_for_status()
    return [HermesJob.model_validate(item) for item in response.json()]
```

```python
class JobSynchronizer:
    def reconcile(self, jobs, snapshot, sequence):
        existing = {
            agent.agent_id: agent
            for agent in snapshot.agents
            if agent.kind == "scheduled"
        }
        incoming = {f"scheduled:{job.id}": job for job in jobs}
        events = []
        for agent_id, job in incoming.items():
            if agent_id not in existing:
                events.append(make_agent_spawned(
                    agent_id=agent_id,
                    kind="scheduled",
                    display_name=job.name,
                    room="automation",
                    sequence=sequence + len(events),
                    status="idle",
                    next_run_at=job.next_run_at,
                ))
            elif existing[agent_id].next_run_at != job.next_run_at:
                events.append(make_agent_state(
                    agent_id, "idle", "automation", sequence + len(events),
                    next_run_at=job.next_run_at,
                ))
        for agent_id in sorted(existing.keys() - incoming.keys()):
            events.append(make_agent_removed(agent_id, sequence + len(events)))
        return events
```

Run reconciliation from the application task group:

```python
async def poll_jobs(self) -> None:
    while True:
        try:
            jobs = await self._client.list_jobs()
            for event in self._jobs.reconcile(
                jobs, self.snapshot(), self._reducer.snapshot.sequence + 1
            ):
                await self.publish(event)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as error:
            await self.publish(make_connection_changed(
                "degraded", str(error), self._reducer.snapshot.sequence + 1
            ))
        await asyncio.sleep(60)
```

A failed poll leaves previous workers in place. Removal occurs only when a successful response omits a previously known job.

- [ ] **Step 4: Verify scheduled-worker behavior**

Run: `uv run --package yume-api pytest apps/api/tests/services/test_jobs.py -q`

Expected: PASS for add, update, remove-after-successful-reconcile, and failed-poll cases.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/yume_api/hermes/client.py apps/api/src/yume_api/services apps/api/tests/services/test_jobs.py
git commit -m "feat: visualize scheduled Hermes workers"
```

### Task 8: Build the Frontend API Client and World Store

**Files:**
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/src/api/socket.ts`
- Create: `apps/web/src/store/world.ts`
- Create: `apps/web/src/store/world.test.ts`
- Modify: `apps/web/package.json`

**Interfaces:**
- Consumes: `WorldEvent`, `WorldSnapshot`, `AgentView` from `@yume/contracts`
- Produces: `useWorldStore`
- Produces: `getBootstrap() -> Promise<BootstrapResponse>`
- Produces: `connectWorldSocket(url, onEvent) -> () => void`

- [ ] **Step 1: Write the failing frontend reducer test**

```ts
import { describe, expect, it } from "vitest";
import { createWorldStore } from "./world";

it("adds and removes an ephemeral worker", () => {
  const store = createWorldStore();
  store.getState().applyEvent(spawnedDelegatedWorker);
  expect(store.getState().agents).toHaveLength(2);

  store.getState().applyEvent({
    ...baseEvent,
    type: "agent.removed",
    agent_id: "delegated:run-1:call-1",
    payload: {},
  });

  expect(store.getState().agents.map((agent) => agent.agent_id)).toEqual(["yume"]);
});
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pnpm --dir apps/web test --run src/store/world.test.ts`

Expected: FAIL because the store does not exist.

- [ ] **Step 3: Implement the Zustand store**

Run: `pnpm --dir apps/web add '@yume/contracts@workspace:*' zustand`

```ts
import { createStore } from "zustand/vanilla";
import type {
  AgentView, ConversationMessage, WorldEvent, WorldSnapshot,
} from "@yume/contracts";

type WorldState = WorldSnapshot & {
  streamingText: string;
  selectedAgentId: string | null;
  applyEvent: (event: WorldEvent) => void;
  selectAgent: (agentId: string | null) => void;
};

export function createWorldStore() {
  return createStore<WorldState>((set) => ({
    sequence: 0,
    connection: "starting",
    telemetry_mode: "standard",
    session_id: null,
    agents: [],
    conversation: [],
    streamingText: "",
    selectedAgentId: null,
    applyEvent: (event) =>
      set((state) => reduceWorldEvent(state, event)),
    selectAgent: (selectedAgentId) => set({ selectedAgentId }),
  }));
}
```

`reduceWorldEvent` must reject stale events where `event.sequence <= state.sequence`, replace all authoritative fields on `snapshot.replaced`, append deltas with the same message ID to `streamingText`, move the final text into `conversation` on `conversation.completed`, and apply agent spawn/state/remove events.

```ts
export function reduceWorldEvent(state: WorldState, event: WorldEvent): WorldState {
  if (event.sequence <= state.sequence) return state;
  if (event.type === "snapshot.replaced") {
    return {
      ...state,
      ...event.payload.snapshot,
      streamingText: "",
      selectedAgentId: state.selectedAgentId,
    };
  }
  if (event.type === "conversation.delta") {
    return {
      ...state,
      sequence: event.sequence,
      streamingText: state.streamingText + event.payload.text,
    };
  }
  if (event.type === "conversation.completed") {
    const message: ConversationMessage = {
      message_id: event.payload.message_id,
      role: "assistant",
      text: event.payload.text,
    };
    return {
      ...state,
      sequence: event.sequence,
      conversation: [...state.conversation, message],
      streamingText: "",
    };
  }
  if (event.type === "conversation.user_added") {
    return {
      ...state,
      sequence: event.sequence,
      conversation: [...state.conversation, {
        message_id: event.payload.message_id,
        role: "user",
        text: event.payload.text,
      }],
    };
  }
  if (event.type === "agent.spawned") {
    const agent: AgentView = {
      agent_id: event.agent_id,
      evidence: event.evidence,
      ...event.payload,
    };
    return { ...state, sequence: event.sequence, agents: [...state.agents, agent] };
  }
  if (event.type === "agent.state_changed") {
    return {
      ...state,
      sequence: event.sequence,
      agents: state.agents.map((agent) =>
        agent.agent_id === event.agent_id ? { ...agent, ...event.payload } : agent
      ),
    };
  }
  if (event.type === "agent.removed") {
    return {
      ...state,
      sequence: event.sequence,
      agents: state.agents.filter((agent) => agent.agent_id !== event.agent_id),
    };
  }
  return { ...state, sequence: event.sequence };
}
```

- [ ] **Step 4: Implement REST and reconnecting WebSocket clients**

```ts
export type BootstrapResponse = {
  world: WorldSnapshot;
  asset_pack: {
    id: string;
    map: string;
    atlas: string;
    anchors: Record<string, { x: number; y: number }>;
    animations: Record<string, number[]>;
    ui?: {
      image: string;
      atlas: string;
      nine_slice: Record<string, [number, number, number, number]>;
    };
  };
};

export async function getBootstrap(): Promise<BootstrapResponse> {
  const response = await fetch("/api/bootstrap");
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function submitTask(text: string): Promise<void> {
  const response = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error(await response.text());
}
```

```ts
export function connectWorldSocket(
  onEvent: (event: WorldEvent) => void,
  onState: (connected: boolean) => void,
) {
  let socket: WebSocket | undefined;
  let cancelled = false;
  let delay = 500;

  const connect = () => {
    socket = new WebSocket(`${location.origin.replace("http", "ws")}/api/events`);
    socket.onopen = () => { delay = 500; onState(true); };
    socket.onmessage = (message) => onEvent(JSON.parse(message.data));
    socket.onclose = () => {
      onState(false);
      if (!cancelled) setTimeout(connect, delay);
      delay = Math.min(delay * 2, 10_000);
    };
  };
  connect();
  return () => { cancelled = true; socket?.close(); };
}
```

- [ ] **Step 5: Verify the frontend data layer**

Run: `pnpm --dir apps/web test --run src/store src/api`

Expected: PASS for snapshots, stale-event rejection, transcript updates, and reconnect backoff.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/api apps/web/src/store apps/web/package.json pnpm-lock.yaml
git commit -m "feat: add frontend world event store"
```

### Task 9: Render the Isometric Office and Animate Agents

**Files:**
- Create: `apps/web/src/game/coordinates.ts`
- Create: `apps/web/src/game/paths.ts`
- Create: `apps/web/src/game/sprites.ts`
- Create: `apps/web/src/game/OfficeScene.ts`
- Create: `apps/web/src/game/OfficeGame.tsx`
- Create: `apps/web/src/game/coordinates.test.ts`
- Create: `apps/web/src/game/paths.test.ts`

**Interfaces:**
- Produces: `tileToWorld(tileX, tileY, tileWidth, tileHeight) -> {x, y}`
- Produces: `findPath(map, from, to) -> GridPoint[]`
- Produces: `OfficeScene.syncAgents(agents: AgentView[])`
- Produces: `OfficeGame({store})`

- [ ] **Step 1: Write failing projection and path tests**

```ts
it("projects isometric tile coordinates", () => {
  expect(tileToWorld(2, 1, 64, 32)).toEqual({ x: 32, y: 48 });
});

it("routes around blocked tiles", () => {
  const path = findPath(
    [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
    { x: 0, y: 1 },
    { x: 2, y: 1 },
  );
  expect(path).not.toContainEqual({ x: 1, y: 1 });
  expect(path.at(-1)).toEqual({ x: 2, y: 1 });
});
```

- [ ] **Step 2: Run game tests and verify failure**

Run: `pnpm --dir apps/web test --run src/game`

Expected: FAIL because projection and pathfinding are missing.

- [ ] **Step 3: Implement pure projection and A* pathfinding**

```ts
export function tileToWorld(
  tileX: number,
  tileY: number,
  tileWidth: number,
  tileHeight: number,
) {
  return {
    x: Math.round((tileX - tileY) * tileWidth / 2),
    y: Math.round((tileX + tileY) * tileHeight / 2),
  };
}
```

Implement `findPath` with Manhattan neighbor expansion on the logical grid, deterministic neighbor order `[NE, SE, SW, NW]`, blocked value `1`, and an empty array when unreachable.

```ts
export function findPath(grid: number[][], start: GridPoint, goal: GridPoint): GridPoint[] {
  const key = ({ x, y }: GridPoint) => `${x},${y}`;
  const neighbors = [{ x: 1, y: -1 }, { x: 1, y: 1 }, { x: -1, y: 1 }, { x: -1, y: -1 }];
  const open: Array<{ point: GridPoint; cost: number; score: number }> = [
    { point: start, cost: 0, score: 0 },
  ];
  const cameFrom = new Map<string, GridPoint>();
  const best = new Map([[key(start), 0]]);
  while (open.length > 0) {
    open.sort((a, b) => a.score - b.score || key(a.point).localeCompare(key(b.point)));
    const current = open.shift()!;
    if (key(current.point) === key(goal)) {
      const path = [current.point];
      while (cameFrom.has(key(path[0]))) path.unshift(cameFrom.get(key(path[0]))!);
      return path;
    }
    for (const delta of neighbors) {
      const next = { x: current.point.x + delta.x, y: current.point.y + delta.y };
      if (!grid[next.y] || grid[next.y][next.x] !== 0) continue;
      const cost = current.cost + 1;
      if (cost >= (best.get(key(next)) ?? Infinity)) continue;
      best.set(key(next), cost);
      cameFrom.set(key(next), current.point);
      open.push({
        point: next,
        cost,
        score: cost + Math.abs(goal.x - next.x) + Math.abs(goal.y - next.y),
      });
    }
  }
  return [];
}
```

- [ ] **Step 4: Create Phaser with pixel-safe settings**

Run: `pnpm --dir apps/web add phaser`

```ts
const game = new Phaser.Game({
  type: Phaser.AUTO,
  parent: container,
  backgroundColor: "#172126",
  pixelArt: true,
  roundPixels: true,
  antialias: false,
  scale: {
    mode: Phaser.Scale.RESIZE,
    autoCenter: Phaser.Scale.CENTER_BOTH,
  },
  scene: [OfficeScene],
});
```

- [ ] **Step 5: Load the validated pack and render six zones**

```ts
preload() {
  const pack = this.registry.get("bootstrap").asset_pack;
  this.load.tilemapTiledJSON("office", `/asset-packs/${pack}/maps/office.json`);
  this.load.image("office-tiles", `/asset-packs/${pack}/tiles/office.png`);
  this.load.atlas(
    "characters",
    `/asset-packs/${pack}/atlases/characters.png`,
    `/asset-packs/${pack}/atlases/characters.json`,
  );
}

create() {
  const map = this.make.tilemap({ key: "office" });
  const tiles = map.addTilesetImage("office", "office-tiles")!;
  for (const name of ["floor", "walls", "furniture-low", "furniture-high"]) {
    map.createLayer(name, tiles)?.setDepth(name === "furniture-high" ? 10_000 : 0);
  }
  this.anchors = this.registry.get("bootstrap").asset_pack.anchors;
  this.syncAgents(this.registry.get("worldStore").getState().snapshot.agents);
  this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
  this.cameras.main.centerOn(map.widthInPixels / 2, map.heightInPixels / 2);
}
```

- [ ] **Step 6: Synchronize sprites from world state**

```ts
syncAgents(agents: AgentView[]) {
  const activeIds = new Set(agents.map((agent) => agent.agent_id));
  for (const agent of agents) this.upsertAgent(agent);
  for (const [id, sprite] of this.agentSprites) {
    if (!activeIds.has(id)) {
      this.walkTo(sprite, this.anchors.lobby, () => sprite.destroy());
      this.agentSprites.delete(id);
    }
  }
}
```

Status-to-animation rules:

```ts
function animationKey(
  agent: AgentView, animations: Record<string, number[]>
): string {
  const role = agent.kind === "delegated" ? "worker" : agent.kind;
  const state = {
    idle: "idle",
    entering: "enter",
    thinking: "think",
    moving: "walk",
    working: "work",
    waiting_approval: "waiting",
    completed: "report",
    failed: "failed",
    exiting: "exit",
    stale: "waiting",
  }[agent.status];
  const preferred = `${role}-${state}-sw`;
  return animations[preferred] ? preferred : `${role}-idle-sw`;
}
```

Render a status marker for `waiting_approval` and `stale`; never invent a missing activity animation.

- [ ] **Step 7: Add sprite click selection and restrained camera controls**

```ts
sprite.setInteractive({ useHandCursor: true });
sprite.on("pointerup", () => this.store.getState().selectAgent(agent.agent_id));
this.input.on("pointerup", (_pointer, targets) => {
  if (targets.length === 0) this.store.getState().selectAgent(null);
});
this.input.on("wheel", (_pointer, _objects, _dx, dy) => {
  const levels = [1, 1.5, 2];
  const current = levels.indexOf(this.cameras.main.zoom);
  const next = Phaser.Math.Clamp(current + Math.sign(dy), 0, levels.length - 1);
  this.cameras.main.setZoom(levels[next]);
});
```

On pointer-down over empty map space, store the camera origin; on pointer-move, subtract the integer pointer delta from `scrollX` and `scrollY`. The reset control calls `fitOffice()` to restore fitted bounds.

- [ ] **Step 8: Verify game logic and browser smoke**

Run:

```bash
pnpm --dir apps/web test --run src/game
pnpm --dir apps/web build
```

Expected: tests and build pass with no texture or TypeScript errors.

- [ ] **Step 9: Commit**

```bash
git add apps/web/src/game apps/web/package.json pnpm-lock.yaml
git commit -m "feat: render animated isometric office"
```

### Task 10: Build the Floating Task UI and Agent Inspector

**Files:**
- Modify: `apps/web/src/app/App.tsx`
- Create: `apps/web/src/app/app.css`
- Create: `apps/web/src/ui/Hud.tsx`
- Create: `apps/web/src/ui/ChatPanel.tsx`
- Create: `apps/web/src/ui/AgentInspector.tsx`
- Create: `apps/web/src/ui/ConnectionOverlay.tsx`
- Create: `apps/web/src/ui/ui.test.tsx`

**Interfaces:**
- Consumes: `useWorldStore`, `submitTask`
- Produces: one-page simulation HUD, collapsible chat, and one inspector

- [ ] **Step 1: Write failing interaction tests**

```tsx
it("submits a trimmed task and clears the input", async () => {
  const user = userEvent.setup();
  render(<ChatPanel onSubmit={submitTask} />);
  await user.type(screen.getByLabelText("Task for Yume"), "  Research Hermes  ");
  await user.click(screen.getByRole("button", { name: "Send task" }));
  expect(submitTask).toHaveBeenCalledWith("Research Hermes");
  expect(screen.getByLabelText("Task for Yume")).toHaveValue("");
});

it("shows evidence and room for the selected sprite", () => {
  render(<AgentInspector agent={delegatedWorker} onClose={() => {}} />);
  expect(screen.getByText("Verified")).toBeInTheDocument();
  expect(screen.getByText("Research library")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run UI tests and verify failure**

Run: `pnpm --dir apps/web test --run src/ui`

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement the HUD and connection treatment**

```tsx
export function Hud({ yume, connection, agentCount, telemetryMode }: HudProps) {
  return (
    <header className="hud">
      <strong>YUME HQ</strong>
      <span>Yume is {humanizeStatus(yume.status)}</span>
      <span>Hermes {connection}</span>
      <span>{agentCount} agents</span>
      <span>Telemetry: {telemetryMode}</span>
      {connection !== "connected" && (
        <div role="status">Hermes disconnected — reconnecting</div>
      )}
    </header>
  );
}
```

Disconnected mode leaves the office visible, adds a non-modal “Hermes disconnected — reconnecting” banner, and disables task submission.

- [ ] **Step 4: Implement the single-session task panel**

Run: `pnpm --dir apps/web add zod`

```tsx
export function ChatPanel({ disabled, transcript, onSubmit }: Props) {
  const [text, setText] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const task = text.trim();
    if (!task) return;
    onSubmit(task);
    setText("");
  };
  return (
    <section aria-label="Task Yume">
      <header>Task Yume</header>
      <div aria-live="polite">{transcript}</div>
      <form onSubmit={submit}>
        <textarea
          aria-label="Task for Yume"
          value={text}
          onChange={(event) => setText(event.target.value)}
          disabled={disabled}
        />
        <button disabled={disabled || !text.trim()} type="submit">Send task</button>
      </form>
    </section>
  );
}
```

Persist only panel size, position, and collapsed state in `localStorage`; never persist task text or Hermes output there.

```ts
const PANEL_KEY = "yume.task-panel.v1";
const PanelStateSchema = z.object({
  x: z.number().int(),
  y: z.number().int(),
  width: z.number().int().min(280).max(720),
  height: z.number().int().min(220).max(720),
  collapsed: z.boolean(),
});
type PanelState = z.infer<typeof PanelStateSchema>;
const loadPanel = (): PanelState => {
  const value = localStorage.getItem(PANEL_KEY);
  return value ? PanelStateSchema.parse(JSON.parse(value)) : defaultPanelState;
};
const savePanel = (state: PanelState) =>
  localStorage.setItem(PANEL_KEY, JSON.stringify(state));
```

- [ ] **Step 5: Implement one contextual sprite inspector**

```tsx
export function AgentInspector({ agent, onClose }: InspectorProps) {
  return (
    <aside className="agent-inspector" aria-label={`${agent.display_name} details`}>
      <button type="button" aria-label="Close agent details" onClick={onClose}>×</button>
      <h2>{agent.display_name}</h2>
      <dl>
        <dt>Role</dt><dd>{humanizeKind(agent.kind)}</dd>
        <dt>Status</dt><dd>{humanizeStatus(agent.status)}</dd>
        <dt>Room</dt><dd>{humanizeRoom(agent.room)}</dd>
        <dt>Evidence</dt><dd>{agent.evidence === "verified" ? "Verified" : "Inferred"}</dd>
        {agent.task_summary && <><dt>Task</dt><dd>{agent.task_summary}</dd></>}
        {agent.next_run_at && <><dt>Next run</dt><dd><time dateTime={agent.next_run_at}>{formatTime(agent.next_run_at)}</time></dd></>}
      </dl>
    </aside>
  );
}
```

The parent passes `onClose={() => selectAgent(null)}`. Derive elapsed time from `started_at` on a 1-second display timer; do not write clock ticks to world state.

```ts
const labels = {
  kind: { yume: "CEO", scheduled: "Scheduled worker", delegated: "Delegated worker" },
  room: {
    ceo: "CEO office", memory: "Memory vault", research: "Research library",
    work: "Work floor", automation: "Automation bay", lobby: "Lobby",
  },
} as const;
const humanizeKind = (kind: AgentView["kind"]) => labels.kind[kind];
const humanizeRoom = (room: AgentView["room"]) => labels.room[room];
const humanizeStatus = (status: AgentView["status"]) => status.replaceAll("_", " ");
const formatTime = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" })
    .format(new Date(iso));
```

- [ ] **Step 6: Apply the immersive one-page layout**

CSS requirements:

```css
html, body, #root { width: 100%; height: 100%; margin: 0; overflow: hidden; }
.app { position: relative; width: 100%; height: 100%; background: #172126; }
.office { position: absolute; inset: 0; }
.hud { position: absolute; inset: 12px 12px auto; }
.chat-panel { position: absolute; right: 16px; bottom: 16px; }
.agent-inspector { position: absolute; left: 16px; top: 64px; }
canvas { image-rendering: pixelated; }
```

Use CSS variables for all final colors so the production UI pack can replace frame textures without changing layout code.

- [ ] **Step 7: Verify UI behavior**

Run: `pnpm --dir apps/web test --run src/ui src/app`

Expected: PASS for submit, collapse, inspector, disconnected state, and panel persistence.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/app apps/web/src/ui
git commit -m "feat: add immersive task and agent UI"
```

### Task 11: Add Diagnostics, Reconnection, and Static Asset Serving

**Files:**
- Modify: `apps/api/src/yume_api/main.py`
- Create: `apps/api/src/yume_api/api/diagnostics.py`
- Modify: `apps/api/src/yume_api/services/world.py`
- Create: `apps/api/tests/api/test_diagnostics.py`
- Create: `apps/web/src/ui/DiagnosticOverlay.tsx`
- Create: `apps/web/src/ui/DiagnosticOverlay.test.tsx`

**Interfaces:**
- Produces: startup state `ready | invalid_config | invalid_assets | hermes_unavailable`
- Produces: `/api/diagnostics`
- Produces: static `/asset-packs/{pack}/...`

- [ ] **Step 1: Write failing diagnostic tests**

```python
def test_invalid_pack_still_serves_diagnostic(client_with_invalid_pack) -> None:
    response = client_with_invalid_pack.get("/api/diagnostics")
    assert response.status_code == 200
    assert response.json() == {
        "status": "invalid_assets",
        "file": "asset-packs/custom/pack.json",
        "message": "missing semantic anchors: ['lobby']",
    }
```

- [ ] **Step 2: Run diagnostic tests and verify failure**

Run: `uv run --package yume-api pytest apps/api/tests/api/test_diagnostics.py -q`

Expected: FAIL because startup diagnostics are absent.

- [ ] **Step 3: Implement startup diagnostics without suppressing the app**

```python
class Diagnostic(BaseModel):
    status: Literal["ready", "invalid_config", "invalid_assets", "hermes_unavailable"]
    file: str | None = None
    message: str = ""

    @classmethod
    def ready(cls):
        return cls(status="ready")

    @classmethod
    def invalid_config(cls, path: Path, error: Exception):
        return cls(status="invalid_config", file=str(path), message=str(error))

    @classmethod
    def invalid_assets(cls, path: Path, error: Exception):
        return cls(status="invalid_assets", file=str(path), message=str(error))

    @classmethod
    def hermes_unavailable(cls, error: Exception):
        return cls(
            status="hermes_unavailable",
            message=f"Hermes connection failed ({type(error).__name__}); verify the local API server.",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.config = load_dashboard_config(settings.dashboard_config)
        pack_path = settings.asset_pack_root / app.state.config.asset_pack
        app.state.asset_pack = load_and_validate_pack(pack_path)
    except ValidationError as error:
        app.state.diagnostic = Diagnostic.invalid_config(settings.dashboard_config, error)
    except AssetPackError as error:
        app.state.diagnostic = Diagnostic.invalid_assets(pack_path / "pack.json", error)
    else:
        try:
            app.state.capabilities = await app.state.hermes.get_capabilities()
            app.state.diagnostic = Diagnostic.ready()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as error:
            app.state.diagnostic = Diagnostic.hermes_unavailable(error)
    yield
    await app.state.hermes.aclose()
```

Do not catch unexpected exceptions; they must fail startup and produce a non-zero container exit.

- [ ] **Step 4: Mount read-only static resources**

```python
app.mount(
    "/asset-packs",
    StaticFiles(directory=settings.asset_pack_root, check_dir=True),
    name="asset-packs",
)
app.mount(
    "/",
    StaticFiles(directory=settings.web_dist, html=True, check_dir=True),
    name="web",
)
```

Register all `/api` and WebSocket routes before the `/` mount.

- [ ] **Step 5: Implement diagnostic UI**

```tsx
export function DiagnosticOverlay({ diagnostic, retry }: Props) {
  if (diagnostic.status === "ready") return null;
  return (
    <section className="diagnostic-overlay" role="alert">
      <h1>{diagnosticTitle[diagnostic.status]}</h1>
      {diagnostic.file && <code>{diagnostic.file}</code>}
      <p>{diagnostic.message}</p>
      {diagnostic.status === "hermes_unavailable" && (
        <button type="button" onClick={retry}>Retry connection</button>
      )}
    </section>
  );
}
```

- [ ] **Step 6: Verify resilience**

Run:

```bash
uv run --package yume-api pytest apps/api/tests/api/test_diagnostics.py -q
pnpm --dir apps/web test --run src/ui/DiagnosticOverlay.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/yume_api apps/api/tests/api/test_diagnostics.py apps/web/src/ui
git commit -m "feat: add startup diagnostics and recovery"
```

### Task 12: Package the Single Production Container

**Files:**
- Create: `infra/docker/Dockerfile`
- Create: `.dockerignore`
- Create: `compose.yaml`
- Create: `.env.example`
- Create: `apps/api/src/yume_api/settings.py`
- Create: `apps/api/tests/test_settings.py`

**Interfaces:**
- Produces: `docker compose up --build`
- Produces: loopback dashboard at `http://127.0.0.1:8000`

- [ ] **Step 1: Write failing settings tests**

```python
def test_api_key_is_required(monkeypatch) -> None:
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_secret_is_not_in_repr(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_API_KEY", "super-secret")
    assert "super-secret" not in repr(Settings())
```

- [ ] **Step 2: Implement Pydantic settings**

```python
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    hermes_api_key: SecretStr
    hermes_base_url: str = "http://127.0.0.1:8642"
    dashboard_config: Path = Path("/config/dashboard.yaml")
    asset_pack_root: Path = Path("/asset-packs")
    data_dir: Path = Path("/data")
    web_dist: Path = Path("/app/web")
```

- [ ] **Step 3: Build the multi-stage image**

```dockerfile
FROM node:24-alpine AS web-build
WORKDIR /src
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web apps/web
COPY packages/contracts packages/contracts
RUN pnpm install --frozen-lockfile
RUN pnpm --dir apps/web build

FROM python:3.13-slim AS runtime
RUN useradd --create-home --uid 10001 yume
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package yume-api
COPY --from=web-build /src/apps/web/dist /app/web
COPY asset-packs /asset-packs
RUN mkdir -p /data && chown -R yume:yume /data
USER yume
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "yume_api.main:app", "--host", "127.0.0.1", "--port", "8000"]
```

Pin the uv image by digest when the lockfile is first committed.

- [ ] **Step 4: Add host-network Compose configuration**

```yaml
services:
  dashboard:
    build:
      context: .
      dockerfile: infra/docker/Dockerfile
    network_mode: host
    env_file: .env
    volumes:
      - ./config/dashboard.yaml:/config/dashboard.yaml:ro
      - ./asset-packs:/asset-packs:ro
      - dashboard-data:/data
    read_only: true
    tmpfs:
      - /tmp
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
      interval: 30s
      timeout: 3s
      retries: 3

volumes:
  dashboard-data:
```

- [ ] **Step 5: Verify the image**

Run:

```bash
docker build -f infra/docker/Dockerfile -t ame-no-uzume:test .
docker image inspect ame-no-uzume:test --format '{{.Config.User}}'
```

Expected: build succeeds and the configured user is `yume`.

- [ ] **Step 6: Commit**

```bash
git add infra/docker .dockerignore compose.yaml .env.example apps/api/src/yume_api/settings.py apps/api/tests/test_settings.py
git commit -m "build: package local dashboard container"
```

### Task 13: Add a Fake Hermes Server and Full End-to-End Flow

**Files:**
- Create: `tests/fake_hermes/app.py`
- Create: `tests/fake_hermes/fixtures/delegated-task.jsonl`
- Create: `tests/e2e/playwright.config.ts`
- Create: `tests/e2e/dashboard.spec.ts`
- Modify: `package.json`
- Modify: `compose.yaml`

**Interfaces:**
- Produces: deterministic Hermes-compatible API for tests
- Produces: `pnpm e2e`

- [ ] **Step 1: Write the failing browser scenario**

```ts
test("delegated worker enters, reports, and leaves", async ({ page }) => {
  await page.goto("http://127.0.0.1:8000");
  await page.getByLabel("Task for Yume").fill("Research Hermes hooks");
  await page.getByRole("button", { name: "Send task" }).click();

  await expect(page.getByText("Delegated Worker")).toBeVisible();
  await expect(page.getByText("Research library")).toBeVisible();
  await expect(page.getByText("Hooks research complete")).toBeVisible();
  await expect(page.getByText("Delegated Worker")).not.toBeVisible();
  await expect(page.getByText("Yume is idle")).toBeVisible();
});
```

- [ ] **Step 2: Run Playwright and verify failure**

Run: `pnpm e2e`

Expected: FAIL because the fake Hermes server and test stack are absent.

- [ ] **Step 3: Implement the minimal Hermes-compatible fake**

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.get("/v1/capabilities")
async def capabilities():
    return {
        "features": {
            "session_chat_stream": True,
            "run_stop": True,
            "run_approval": True,
        }
    }


@app.post("/api/sessions")
async def create_session():
    return {"id": "session-e2e"}


@app.post("/api/sessions/{session_id}/chat/stream")
async def stream_chat(session_id: str):
    async def events():
        for line in Path("tests/fake_hermes/fixtures/delegated-task.jsonl").read_text().splitlines():
            payload = json.loads(line)
            yield f"event: {payload['event']}\ndata: {json.dumps(payload['data'])}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
```

- [ ] **Step 4: Cover the required v1 scenarios**

Add one deterministic fixture and assertion set per row:

| Test name | Fake input | Required assertion |
|---|---|---|
| `initial connection` | capabilities + empty session | connected badge and `Yume is idle` |
| `text task streaming` | two `assistant.delta` events | concatenated response appears in order |
| `delegated lifecycle` | delegate start/completion | worker enters, reports, then disappears |
| `scheduled discovery` | one `/api/jobs` result | persistent automation worker appears |
| `approval resolved` | approval event + approval response | approval control clears after decision |
| `failed run` | `run.failed` | failed marker appears and Yume returns idle |
| `reconnect snapshot` | one forced socket close | disconnected badge then fresh snapshot |
| `invalid asset` | invalid pack environment | exact diagnostic file and message |
| `session reset` | reset response | new session ID is used for the next task |

Each fixture is a checked-in JSONL file selected through `FAKE_HERMES_SCENARIO`; tests must not use arbitrary sleeps. Wait on visible state or API responses.

```ts
const passiveScenarios = [
  ["initial-connection", "Yume is idle"],
  ["streaming", "First second final"],
  ["scheduled-job", "Daily memory"],
  ["failed-run", "Task failed"],
  ["invalid-assets", "missing semantic anchors: ['lobby']"],
] as const;

for (const [scenario, expected] of passiveScenarios) {
  test(scenario, async ({ page }) => {
    await page.goto(`http://127.0.0.1:8000/?scenario=${scenario}`);
    await expect(page.getByText(expected)).toBeVisible();
  });
}

test("approval resolves", async ({ page }) => {
  await page.goto("http://127.0.0.1:8000/?scenario=approval");
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("button", { name: "Approve" })).not.toBeVisible();
});

test("session reset replaces the active session", async ({ page }) => {
  await page.goto("http://127.0.0.1:8000/?scenario=session-reset");
  const reset = page.waitForResponse("**/api/session/reset");
  await page.getByRole("button", { name: "Reset conversation" }).click();
  expect((await reset).status()).toBe(200);
  await expect(page.getByText("Conversation reset")).toBeVisible();
});
```

- [ ] **Step 5: Run the complete browser suite**

Run: `pnpm e2e`

Expected: all scenarios pass on Chromium.

- [ ] **Step 6: Commit**

```bash
git add tests package.json pnpm-lock.yaml compose.yaml
git commit -m "test: cover dashboard with fake Hermes"
```

### Task 14: Add Contributor Documentation and Local V1 Release Checks

**Files:**
- Create: `README.md`
- Create: `CONTRIBUTING.md`
- Create: `docs/release-checklist.md`
- Modify: `Makefile`
- Modify: `AGENTS.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces: documented macOS setup and contribution workflow
- Produces: `make verify` and a manual host-network release checklist

- [ ] **Step 1: Verify the local release target is absent**

Run: `make verify`

Expected: FAIL with `No rule to make target 'verify'`.

- [ ] **Step 2: Add the local verification target**

```make
.PHONY: verify

verify:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) build
	pnpm e2e
	docker build -f infra/docker/Dockerfile -t ame-no-uzume:release-candidate .
```

Do not create `.github/workflows/` or any deployment automation in this task.

- [ ] **Step 3: Document exact macOS installation**

README setup sequence:

```text
1. Install Docker Desktop 4.34+.
2. Enable Settings → Resources → Network → Enable host networking.
3. Enable the Hermes API server on 127.0.0.1:8642 with an API key.
4. Copy .env.example to .env and config/dashboard.example.yaml to config/dashboard.yaml.
5. Run docker compose up --build.
6. Open http://127.0.0.1:8000.
```

Include explicit warnings that Hermes grants terminal and file-tool access, the dashboard is loopback-only, and Tailscale exposure is not configured by the project.

- [ ] **Step 4: Update repository guidance**

Replace planning-phase wording in `AGENTS.md` with the implemented monorepo structure and verified commands. Retain the language-convention skill gates; the per-non-commit-step Sol review and Terra correction protocol; the two-loop maximum and its Critical, Important, and Minor-finding outcomes; the final Commit-step sequence of verification, accumulated-diff review, correction/re-review, and plan-checklist updates before commit with no post-commit review; the task-level commit-and-push policy; direct `main` workflow; and pre-v1 CI/CD prohibition. Document Python `snake_case`, TypeScript `camelCase`/React `PascalCase`, Ruff, ty, ESLint, Vitest, pytest, Playwright, and Conventional Commits.

- [ ] **Step 5: Run fresh final verification**

Run:

```bash
make verify
```

Expected: every command exits 0.

- [ ] **Step 6: Perform the manual macOS smoke test**

Verify:

```text
Docker Desktop host networking reaches native Hermes on 127.0.0.1:8642
dashboard is reachable only at host loopback
one session survives container restart
Yume, scheduled workers, and delegated workers animate correctly
disconnect and reconnect reconcile without invented workers
custom placeholder pack mount is read-only
no .github/workflows directory or other CI/CD configuration exists
```

- [ ] **Step 7: Commit**

```bash
git add README.md CONTRIBUTING.md docs/release-checklist.md Makefile AGENTS.md .gitignore
git commit -m "docs: add contributor and local release workflow"
```

## Core Completion Gate

Run these commands from a clean checkout:

```bash
uv sync --frozen --all-packages
pnpm install --frozen-lockfile
make lint
make test
make build
pnpm e2e
docker build -f infra/docker/Dockerfile -t ame-no-uzume:core-complete .
git status --short
test ! -d .github/workflows
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

Expected: all commands exit 0, the worktree is clean, no CI/CD workflow exists, and local `main` matches `origin/main`.
