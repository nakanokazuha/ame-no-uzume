FROM node:24-alpine AS web-build

WORKDIR /src

RUN corepack enable

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml tsconfig.base.json ./
COPY apps/web apps/web
COPY packages/contracts packages/contracts

RUN pnpm install --frozen-lockfile
RUN pnpm --dir apps/web build


FROM python:3.13-slim AS runtime

RUN useradd --create-home --uid 10001 yume

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api

RUN uv sync --frozen --no-dev --package yume-api

COPY --from=web-build /src/apps/web/dist /app/web
COPY asset-packs /asset-packs

RUN mkdir -p /data && chown -R yume:yume /data

USER yume

ENV PATH="/app/.venv/bin:$PATH" \
    YUME_DASHBOARD_CONFIG=/config/dashboard.yaml \
    YUME_ASSET_PACK_ROOT=/asset-packs \
    YUME_WEB_DIST=/app/web

EXPOSE 8000

CMD ["uvicorn", "yume_api.main:app", "--host", "127.0.0.1", "--port", "8000"]
