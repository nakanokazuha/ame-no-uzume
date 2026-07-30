# Repository Guidelines

## Project Status and Source of Truth

Yume is a macOS-first React/Vite + Phaser frontend and FastAPI Hermes adapter
visualized as an isometric pixel-art office. The implemented monorepo and
approved product decisions are described in the design and roadmap documents
under `docs/superpowers/`; the current task plan is
`docs/superpowers/plans/2026-07-27-yume-dashboard-core.md`. Keep those planning
artifacts and `HANDOVER.md` local; they are intentionally ignored and must not
be committed or pushed.

Core v1 work is implemented through Task 14. Treat the plan gates and this file
as requirements, and update the local plan whenever implementation status
changes.

## Implemented Repository Structure

- `apps/api/`: FastAPI adapter, Hermes client, domain services, and pytest tests.
- `apps/web/`: React/Vite UI and Phaser office renderer.
- `packages/contracts/`: generated TypeScript event contracts; regenerate from
  the source models instead of hand-editing generated files.
- `asset-packs/<pack-id>/`: declarative, read-only asset packs.
- `config/`: dashboard configuration examples and local overrides.
- `infra/`: Docker image definition.
- `tests/fake_hermes/`: deterministic fake Hermes fixtures and server.
- `tests/e2e/`: Playwright browser coverage.

React owns floating interface components. Phaser owns the isometric world and
its interaction layer. The backend alone communicates with Hermes and owns the
API key. Keep the product as one immersive, map-first page: do not introduce a
router, tabs, sidebar, pagination, settings page, map editor, multi-session chat,
or analytics suite without an approved plan change.

## Local Requirements and Commands

Supported local tooling is Python 3.13 with `uv`, Node.js 24 LTS with pnpm,
Docker Desktop 4.34+ with host networking enabled, and a native Hermes API on
`127.0.0.1:8642`.

Verified root commands:

- `make dev`: run the local FastAPI and Vite development servers.
- `make test`: run pytest and the frontend Vitest suite.
- `make lint`: run Ruff, ty, frontend lint, and TypeScript checks.
- `make build`: build the frontend and Python package.
- `pnpm e2e`: run deterministic Playwright tests against fake Hermes.
- `make verify`: run lint, test, build, E2E, and the release-candidate Docker
  build.

Run `uv sync --frozen --all-packages` and `pnpm install --frozen-lockfile` when
preparing a fresh checkout. The exact macOS setup and final host-network smoke
checks are in [README.md](README.md) and
[`docs/release-checklist.md`](docs/release-checklist.md).

Do not add `.github/workflows/`, deployment automation, or other CI/CD before
the complete v1 acceptance gate passes.

## Coding, Types, and Assets

- Use four-space Python indentation and two-space TypeScript/TSX indentation.
- Use `snake_case` for Python, `camelCase` for TypeScript values and functions,
  `PascalCase` for React components and types, and `kebab-case` for web assets.
- Apply Ruff and ty to Python; apply ESLint/Oxlint and strict TypeScript checks
  to frontend code.
- Preserve the shared 64×32 isometric tile and 32×48 character-frame contract.
- Asset packs contain data and artwork only, never executable browser code.
- AI-generated art is reference material; shipped pixels require Aseprite
  cleanup, deterministic export, validation, and in-engine review.
- Hermes events are authoritative. Use generic inferred states only when data
  is incomplete; never invent an observed action, tool, role, task, or result.
- Never expose Hermes credentials to the browser or logs. Keep services
  loopback-only, retain read-only mounts, and leave Tailscale exposure outside
  this project.

## Testing and Task Workflow

Develop behavior test-first for implementation tasks. Use pytest for backend
units and adapters, Vitest and Testing Library for frontend behavior, and
Playwright with deterministic fake-Hermes fixtures for integration flows. The
default tests must never require a live Hermes instance.

Before Python work, load `python-conventions`; before TypeScript, TSX, or
related JavaScript work, load `typescript-convention`; load both for mixed
tasks. Apply their type-safety, dependency-management, testing, and structure
rules without silently changing tools or architecture outside the task.

Every `gpt-5.6-terra` and `gpt-5.6-sol` implementation or review agent uses
`high` reasoning; reserve `xhigh` for a future Luna agent. For numbered
implementation steps, dispatch a fresh read-only Sol reviewer using
`superpowers:requesting-code-review` before checking or advancing the step. If
valid Critical or Important findings appear, dispatch a fresh Terra correction
agent using `superpowers:receiving-code-review`, fixing and testing one item at
a time, then dispatch another fresh Sol reviewer. Allow at most two
correction/re-review loops per gate. If Critical or Important findings remain,
stop and request user direction; record Minor findings for later.

For the final Commit step, finish verification, request a fresh Sol review of
the accumulated task diff, resolve valid findings with correction/re-review,
update the local plan checklists, and only then create the focused commit. No
post-commit review is intended. A task is complete only after all steps are
checked, its focused Conventional Commit is created, and `git push origin main`
succeeds. Work directly on `main`; do not create feature branches or partial
commits unless the user explicitly changes this policy.

Use Conventional Commit messages such as `feat: ...`, `fix: ...`, `test: ...`,
`build: ...`, and `docs: ...`. Keep each task commit focused, verify the full
task before committing, and push `main` after every completed task.
