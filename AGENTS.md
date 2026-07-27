# Repository Guidelines

## Project Status & Source of Truth

The repository contains the approved design, implementation plans, and the initial monorepo plus event-contract implementation. Read `docs/superpowers/specs/2026-07-27-yume-dashboard-design.md`, then `docs/superpowers/plans/2026-07-27-yume-dashboard-roadmap.md`. Execute the core plan before the optional bridge or production assets. Treat plan gates as requirements; update documentation when implementation diverges.

## Planned Project Structure

The monorepo places FastAPI in `apps/api/`, React/Vite and Phaser in `apps/web/`, and generated event types in `packages/contracts/`. Asset packs belong in `asset-packs/<pack-id>/`; editable sources belong in `art/`. Keep configuration in `config/`, Docker files in `infra/`, fake-Hermes fixtures in `tests/fake_hermes/`, browser tests in `tests/e2e/`, and documentation in `docs/`.

## Build, Test, and Development Commands

These commands become available during Core Task 1:

- `make dev`: run the API and Vite development servers.
- `make test`: run Python and TypeScript tests.
- `make lint`: run Ruff, mypy, ESLint, and TypeScript checks.
- `make build`: build the frontend and Python package.
- `pnpm e2e`: run Playwright against fake Hermes.
- `make assets-export` / `make assets-validate`: export and validate production artwork after the asset plan adds them.

Until a command exists, use the exact task command from the relevant implementation plan.

## Coding and Architecture Rules

Use four-space Python indentation and two-space TypeScript/TSX indentation. Use `snake_case` for Python, `camelCase` for TypeScript values, `PascalCase` for React components and types, and `kebab-case` for web assets. React owns floating interface components; Phaser owns the office world. The backend alone communicates with Hermes. Do not hand-edit generated contract files; change Pydantic models and regenerate them. Asset packs are declarative and must not contain executable browser code.

## Testing and Assets

Develop behavior test-first. Use pytest for backend units and adapters, Vitest and Testing Library for frontend behavior, and Playwright with deterministic fake-Hermes fixtures for integration flows. Never require a live Hermes instance in default tests. Preserve the shared 64×32 tile and 32×48 character contract. AI-generated art is reference material only; shipped pixels require Aseprite cleanup, deterministic export, validation, and in-engine review.

## Subagent Execution

When implementation work is delegated, use only the approved `gpt-5.6-luna` model with `xhigh` reasoning. Do not substitute another model; if that model is unavailable, pause and request direction. Use a fresh implementer and reviewer for each task, and keep all work on the shared `main` branch. After a task passes review and verification, mark that task complete in its implementation-plan checklist before creating the task's commit and pushing `origin/main`.

## Commits, Delivery, and Security

The remote is `https://github.com/nakanokazuha/ame-no-uzume.git`; implementation proceeds directly on `main`. Verify a complete task before creating its focused Conventional Commit; never commit a partial step. Push `main` to `origin` after every task. Do not add CI/CD until the v1 acceptance gate passes. Never expose Hermes credentials to the browser or logs. Keep services loopback-only, retain read-only mounts, and leave Tailscale exposure outside this project.
