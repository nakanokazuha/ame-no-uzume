# Optional Hermes observability hook

This standalone, standard-library hook forwards limited `subagent_start` and
`subagent_stop` telemetry to a Yume dashboard. It is optional: request or
network failures return `{}` so Hermes can continue without dashboard
telemetry.

## Configure

Set the dashboard endpoint and shared hook token in the Hermes process
environment. Keep the token out of Hermes configuration files, command-line
arguments, and logs.

```sh
export YUME_HOOK_URL="http://127.0.0.1:8000/api/integrations/hermes/events"
export YUME_HOOK_TOKEN="replace-with-the-same-value-as-the-dashboard"
```

Install the emitter, which creates `~/.hermes/agent-hooks` if needed and copies
the script as `yume-observer.py` with mode `0700`:

```sh
./integrations/hermes-hook/install.sh
```

The installer only prints this configuration. Add it to Hermes yourself; it
never edits Hermes configuration automatically.

```yaml
hooks:
  subagent_start:
    - command: "~/.hermes/agent-hooks/yume-observer.py subagent_start"
      timeout: 2
  subagent_stop:
    - command: "~/.hermes/agent-hooks/yume-observer.py subagent_stop"
      timeout: 2
```

## Privacy boundary

Only these source fields can leave Hermes:

- `subagent_start`: `child_session_id`, `child_subagent_id`, `child_role`,
  `child_goal`
- `subagent_stop`: `child_session_id`, `child_subagent_id`, `child_role`, `child_status`,
  `duration_ms`, and reduced `tool_call_history`

For accepted tool history, each entry is reduced to only `tool_name` and
`status`. Credentials, raw tool results, child summaries, and every other
field are omitted.

When Hermes supplies both IDs at start, Yume uses `child_session_id` as the
worker identity because native stop hooks retain it. Older hook payloads that
only contain `child_subagent_id` remain supported.

## Verify

With the environment variables set and the dashboard running, use Hermes'
diagnostics:

```sh
hermes hooks doctor
hermes hooks test subagent_start \
  --payload-file integrations/hermes-hook/tests/fixtures/start.json
```

The hook prints `{}` on stdout, should finish below the configured two-second
limit, and should produce one accepted dashboard event.
