# Contributing to Yume

## Before changing code

Read `AGENTS.md`, the approved design, and the relevant section of
`docs/superpowers/plans/2026-07-27-yume-dashboard-core.md`. Keep the product
map-first and preserve the boundary that FastAPI alone communicates with
Hermes. Planning documents and `HANDOVER.md` are local-only; do not stage them.

For Python changes, load `python-conventions`. For TypeScript, TSX, or related
JavaScript changes, load `typescript-convention`; load both for mixed work.
Follow the skill gates and the task plan rather than introducing unplanned
architecture.

## Development setup

```bash
uv sync --frozen --all-packages
pnpm install --frozen-lockfile
cp .env.example .env
cp config/dashboard.example.yaml config/dashboard.yaml
```

Set `HERMES_API_KEY` only in the local `.env` or process environment. Never
commit it, print it, or send it to the browser. Docker Desktop host networking
must be enabled for the native Hermes service at `127.0.0.1:8642`.

## Checks

Use the smallest relevant check while iterating, then run the full task gate
before committing:

```bash
make lint       # Ruff, ty, Oxlint, and TypeScript
make test       # pytest and Vitest
make build      # Vite and Python package builds
pnpm e2e        # deterministic Chromium tests with fake Hermes
make verify     # all checks plus release-candidate Docker build
```

Backend tests use pytest, frontend behavior tests use Vitest and Testing
Library, and browser flows use Playwright. Default tests do not require live
Hermes. Do not hand-edit generated files in `packages/contracts`; update source
models and regenerate them.

## Architecture and asset rules

React owns floating panels and controls; Phaser owns the isometric office and
interaction layer. Hermes events are authoritative. Generic inferred states
are acceptable only when telemetry is incomplete and must never claim an
unobserved action, task, tool, role, or result.

Use four-space Python indentation and two-space TypeScript/TSX indentation;
`snake_case` in Python, `camelCase` for TypeScript values/functions,
`PascalCase` for React components/types, and `kebab-case` for web assets.
Asset packs are read-only declarative data and artwork. Preserve the 64×32 tile
and 32×48 character-frame contract. AI-generated artwork is reference material
until it has been cleaned up, exported deterministically, validated, and
reviewed in-engine.

## Task and commit workflow

Work directly on `main`. A task is the delivery unit: update the local plan,
complete its checks, make one focused Conventional Commit, and push
`origin/main`. Do not create partial commits or feature branches unless the
user explicitly changes this policy. Do not add `.github/workflows/` or other
CI/CD before the full v1 acceptance gate passes.

For implementation tasks, follow the plan's test-first and review gates: each
numbered non-commit step receives a fresh read-only Sol review; valid Critical
or Important findings receive one-at-a-time Terra corrections and a fresh Sol
re-review; allow at most two loops and stop for user direction if such findings
remain. The final Commit step requires verification, accumulated-diff review,
valid corrections/re-review, and plan-checklist updates before commit; there is
no post-commit review.

Use Conventional Commit prefixes (`feat:`, `fix:`, `test:`, `build:`,
`docs:`). Keep review and test output with the task handover. Report any
environment-only limitation separately from product failures.
