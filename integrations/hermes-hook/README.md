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

`YUME_HOOK_URL` must be an `http://` URL with a literal loopback IP address:
an address in `127.0.0.0/8` or `[::1]`. The emitter rejects hostnames,
non-loopback destinations, credentials in the URL, and redirects.

Install the emitter, which creates `~/.hermes/agent-hooks` if needed and copies
the script as `yume-observer.py` with mode `0700`:

```sh
./integrations/hermes-hook/install.sh
```

The installer only prints this configuration. Merge its two event entries into
your existing top-level `hooks:` mapping; do not paste a second `hooks:` key or
replace unrelated hook entries. The installer never edits Hermes configuration
automatically.

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

## Approve and verify

Hermes 0.18.2 records approval when a normally started agent first encounters
each configured shell-hook command on a TTY. Start a normal Hermes agent and
approve only the displayed Yume observer commands for both `subagent_start`
and `subagent_stop`. For a deliberate non-interactive approval, start that
normal agent with `hermes --accept-hooks` or set `HERMES_ACCEPT_HOOKS=1` for
that process.

`hermes hooks test` runs a hook that is already configured; it neither starts
an agent nor creates an approval entry. After approval, use it only as a
transport check and use `doctor` to verify both configured events are
allowlisted:

```sh
hermes hooks doctor
hermes hooks test subagent_start \
  --payload-file integrations/hermes-hook/tests/fixtures/start.json
hermes hooks test subagent_stop \
  --payload-file integrations/hermes-hook/tests/fixtures/stop.json
```

Confirm `hermes hooks doctor` reports the `subagent_start` and `subagent_stop`
observer commands as allowlisted. Each test prints `{}` on stdout, should
finish below the configured two-second limit, and should produce one accepted
dashboard event.

To remove the opt-in, delete both configuration entries, revoke the two exact
observer commands with `hermes hooks revoke`, remove the emitter, and unset the
hook environment variables. Revocation applies to newly started Hermes CLI or
gateway processes; restart the relevant Hermes process because callbacks
already registered in a running process remain active until it restarts.
