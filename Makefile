.PHONY: dev test lint build

dev:
	concurrently --kill-others \
		"uv run --package yume-api uvicorn yume_api.main:app --reload --port 8000" \
		"pnpm --dir apps/web dev"

test:
	uv run --package yume-api pytest apps/api/tests
	pnpm test

lint:
	cd apps/api && uv run ruff format --check .
	cd apps/api && uv run ruff check .
	cd apps/api && uv run ty check src tests
	pnpm lint
	pnpm typecheck

build:
	pnpm build
	uv build --package yume-api
