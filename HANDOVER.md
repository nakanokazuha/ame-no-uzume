# Yume Handover

## Current state

- Repository: `/Users/user/Documents/Yume/ame-no-uzume`
- Branch: `main`, pushed to `origin/main`
- Latest commit: `797c9da feat: render animated isometric office`
- Working tree was clean after Task 9 verification.
- `HANDOVER.md` is intentionally tracked so another session can resume here.

## Product and architecture

Yume is a macOS-first React/Vite + FastAPI dashboard that visualizes Hermes as
an isometric pixel-art office. FastAPI is the only Hermes client and owns the
credential. React owns floating interface components; Phaser owns the
isometric world. Both consume the frontend world store. Telemetry is
verified-first: real Hermes events are authoritative; generic inference is
allowed only when telemetry is incomplete and must not invent observed
actions. Keep services localhost/loopback-oriented and never expose Hermes
credentials to the browser or logs.

## Completed Core tasks

- Task 1: monorepo foundation and commands — `67177a9`
- Task 2: shared contracts — `dd28233`, `fe31b2a`, `15f71a3`
- Task 3: placeholder asset pack — `0fc5218`, `64b82b1`
- Task 4: Hermes adapter and persistent session — `bccc25c`, `badbec2`
- Task 5: normalization and reducer — `7414d67`, `f9fdf08`, `f3d103c`, `629c9a6`
- Task 6: world service, REST routes, WebSocket — `c590c57`
- Task 7: scheduled Hermes workers — `01048e1`
- Task 8: frontend API client and Zustand world store — `2cdd413`
- Task 9: Phaser office renderer and agent animation — `797c9da`

Task 9 provides:

- `apps/web/src/game/coordinates.ts` — isometric projection
- `apps/web/src/game/paths.ts` — deterministic A* pathfinding
- `apps/web/src/game/sprites.ts` — animation fallback, status markers, pixel snapping
- `apps/web/src/game/OfficeScene.ts` — tilemap, atlas, layers, sprites, camera
- `apps/web/src/game/OfficeGame.tsx` — Phaser lifecycle wrapper

## Next task: Task 10

Task 10 is **Build the Floating Task UI and Agent Inspector**. Use the Core
plan at `docs/superpowers/plans/2026-07-27-yume-dashboard-core.md`, beginning
at the `### Task 10` section. Planned files:

- Modify `apps/web/src/app/App.tsx`
- Create `apps/web/src/app/app.css`
- Create `apps/web/src/ui/Hud.tsx`
- Create `apps/web/src/ui/ChatPanel.tsx`
- Create `apps/web/src/ui/AgentInspector.tsx`
- Create `apps/web/src/ui/ConnectionOverlay.tsx`
- Create `apps/web/src/ui/ui.test.tsx`

Task 10 consumes `useWorldStore` and `submitTask`, keeps the page map-first,
adds restrained floating HUD/chat/inspector UI, shows connection degradation
without hiding the office, and never persists task text or Hermes output in
localStorage. Follow the written plan for the exact interaction and layout
requirements.

## Required workflow

- Before TypeScript/TSX work, read `/Users/user/.codex/skills/typescript-convention/SKILL.md`.
- Use TDD and keep generated contracts untouched.
- Use a fresh Terra implementer and fresh Sol read-only reviewer for each task.
- Resolve valid Critical/Important review findings with a fresh Terra correction
  and fresh Sol re-review; allow at most two correction loops.
- Run focused tests, then the relevant repository gates before committing.
- Commit focused Conventional Commits on `main` and push `origin/main`.
- Update the local Core plan checklist and `.superpowers/sdd/...` report/ledger;
  these planning directories are ignored intentionally and are not pushed.

## Verification note

Backend verification has passed with `make test` (138 tests, 91.53% coverage).
The root Makefile's pnpm step can fail in this environment because the pinned
`pnpm@10.12.4` release cannot be fetched/verified by its registry-signature
check. When that happens, run the installed binaries directly from
`apps/web/node_modules/.bin` for Vitest, `tsc`, `oxlint`, and Vite, and report
the wrapper limitation separately from application failures.

## Useful files

- `AGENTS.md` — repository rules and task workflow
- `docs/superpowers/specs/2026-07-27-yume-dashboard-design.md` — approved design
- `docs/superpowers/plans/2026-07-27-yume-dashboard-core.md` — Core task plan
- `asset-packs/placeholder/pack.json` — validated placeholder asset manifest
- `apps/web/src/store/world.ts` — frontend authoritative world state
- `apps/api/src/yume_api/services/world.py` — backend world service
