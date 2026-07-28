# Repository Guidelines

## Project Status & Source of Truth

The repository contains the approved design, implementation plans, and the implemented monorepo, event contracts, configuration, and placeholder asset pack. Read `docs/superpowers/specs/2026-07-27-yume-dashboard-design.md`, then `docs/superpowers/plans/2026-07-27-yume-dashboard-roadmap.md`. Execute the core plan before the optional bridge or production assets. Treat plan gates as requirements; update documentation when implementation diverges.

## Planned Project Structure

The monorepo places FastAPI in `apps/api/`, React/Vite and Phaser in `apps/web/`, and generated event types in `packages/contracts/`. Asset packs belong in `asset-packs/<pack-id>/`; editable sources belong in `art/`. Keep configuration in `config/`, Docker files in `infra/`, fake-Hermes fixtures in `tests/fake_hermes/`, browser tests in `tests/e2e/`, and documentation in `docs/`.

## Build, Test, and Development Commands

These commands become available during Core Task 1:

- `make dev`: run the API and Vite development servers.
- `make test`: run Python and TypeScript tests.
- `make lint`: run Ruff, ty, ESLint, and TypeScript checks.
- `make build`: build the frontend and Python package.
- `pnpm e2e`: run Playwright against fake Hermes.
- `make assets-export` / `make assets-validate`: export and validate production artwork after the asset plan adds them.

Until a command exists, use the exact task command from the relevant implementation plan.

## Coding and Architecture Rules

Use four-space Python indentation and two-space TypeScript/TSX indentation. Use `snake_case` for Python, `camelCase` for TypeScript values, `PascalCase` for React components and types, and `kebab-case` for web assets. React owns floating interface components; Phaser owns the office world. The backend alone communicates with Hermes. Do not hand-edit generated contract files; change Pydantic models and regenerate them. Asset packs are declarative and must not contain executable browser code.

## Testing and Assets

Develop behavior test-first. Use pytest for backend units and adapters, Vitest and Testing Library for frontend behavior, and Playwright with deterministic fake-Hermes fixtures for integration flows. Never require a live Hermes instance in default tests. Preserve the shared 64×32 tile and 32×48 character contract. AI-generated art is reference material only; shipped pixels require Aseprite cleanup, deterministic export, validation, and in-engine review.

## Subagent Execution

Before each task, load `python-conventions` for Python work and `typescript-convention` for TypeScript, TSX, or related JavaScript work; load both for mixed-language tasks. Apply their type-safety, dependency-management, testing, and structure rules without silently changing tools or architecture outside the task.

Every `gpt-5.6-terra` and `gpt-5.6-sol` agent uses `high` reasoning, including implementation and correction subagents plus initial, re-review, and final accumulated-diff reviewers. Reserve `xhigh` reasoning for a future Luna agent only. Each non-commit numbered step must be reviewed before it is checked or advanced: dispatch a fresh read-only `gpt-5.6-sol` reviewer using `superpowers:requesting-code-review`. Review the current step against its requirements and working-tree diff. If Critical or Important findings are valid, dispatch a fresh `gpt-5.6-terra` correction subagent using `superpowers:receiving-code-review`; it must verify the feedback, fix one item at a time, and test each fix. Then dispatch another fresh Sol reviewer.

Allow at most two correction/re-review loops per review gate. If Critical or Important findings remain after two loops, stop and request user direction; record Minor findings for later. For the final Commit step, complete task verification, request a fresh Sol review of the accumulated task diff, resolve valid findings and re-review, update the plan checklists, and only then create the focused commit; no post-commit review is intended. Keep all work on shared `main`, then push `origin/main`.

## Commits, Delivery, and Security

The remote is `https://github.com/nakanokazuha/ame-no-uzume.git`; implementation proceeds directly on `main`. Verify a complete task before creating its focused Conventional Commit; never commit a partial step. Push `main` to `origin` after every task. Do not add CI/CD until the v1 acceptance gate passes. Never expose Hermes credentials to the browser or logs. Keep services loopback-only, retain read-only mounts, and leave Tailscale exposure outside this project.
