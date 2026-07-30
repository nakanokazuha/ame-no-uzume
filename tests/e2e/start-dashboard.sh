#!/usr/bin/env bash

set -euo pipefail

fake_pid=""
dashboard_pid=""

cleanup() {
  local exit_status=$?
  trap - EXIT INT TERM

  for pid in "$dashboard_pid" "$fake_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done

  exit "$exit_status"
}

trap cleanup EXIT INT TERM

uv run --package yume-api uvicorn tests.fake_hermes.app:app --host 127.0.0.1 --port 8642 &
fake_pid=$!

for attempt in {1..100}; do
  if ! kill -0 "$fake_pid" 2>/dev/null; then
    wait "$fake_pid" || true
    echo "Fake Hermes exited before becoming ready" >&2
    exit 1
  fi
  if curl --fail --silent --output /dev/null http://127.0.0.1:8642/v1/capabilities; then
    break
  fi
  if [[ "$attempt" == "100" ]]; then
    echo "Timed out waiting for Fake Hermes readiness" >&2
    exit 1
  fi
  sleep 0.1
done

uv run --package yume-api uvicorn yume_api.main:app --host 127.0.0.1 --port 8000 &
dashboard_pid=$!
wait "$dashboard_pid"
