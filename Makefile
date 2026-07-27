.PHONY: dev test lint build

dev:
	concurrently --kill-others \
		"uv run --package yume-api uvicorn yume_api.main:app --reload --port 8000" \
		"pnpm --dir apps/web dev"

test:
	uv run --package yume-api pytest
	pnpm test

lint:
	uv run --package yume-api ruff check apps/api
	uv run --package yume-api mypy apps/api/src
	pnpm lint
	pnpm typecheck

build:
	pnpm build
	uv build --package yume-api
