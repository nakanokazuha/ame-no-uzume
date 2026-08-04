# Yume / Ame-no-Uzume

Yume is a macOS-first dashboard for one persistent Hermes session. It renders
verified Hermes activity as an isometric pixel-art office: React owns the
floating interface, Phaser owns the office world, and FastAPI is the only
process that talks to Hermes.

## Security boundary

Hermes can grant terminal and file-tool access to the model. Run it only with
credentials and permissions you intend to delegate. The Hermes API key is
server-side only and must never appear in browser code, browser storage, or
logs. The dashboard and Hermes are configured for host loopback access;
Tailscale exposure is not configured by this project.

## macOS quick start

1. Install Docker Desktop 4.34+.
2. Enable **Settings → Resources → Network → Enable host networking**.
3. Enable the Hermes API server on `127.0.0.1:8642` with an API key.
4. Copy `.env.example` to `.env` and
   `config/dashboard.example.yaml` to `config/dashboard.yaml`; set
   `HERMES_API_KEY` in `.env`.
5. Run `docker compose up --build`.
6. Open <http://127.0.0.1:8000>.

The Compose service mounts the asset pack and dashboard configuration
read-only, keeps its data in a named volume, and binds the application to
`127.0.0.1`. Stop it with `docker compose down`.

## Local development

Install the pinned toolchains, then install dependencies:

```bash
uv sync --frozen --all-packages
pnpm install --frozen-lockfile
```

With a local Hermes server and `HERMES_API_KEY` available, `make dev` starts
FastAPI and Vite. The normal checks are:

```bash
make lint
make test
make build
pnpm e2e
```

`pnpm e2e` starts a deterministic fake Hermes server and uses checked-in JSONL
fixtures; it does not contact a live Hermes instance. `make verify` runs all of
those checks plus the release-candidate Docker build.

## Optional Hermes observability hook

Standard Hermes stream telemetry works without any hook configuration. To opt
in to verified delegated-worker role and goal telemetry, set one shared secret
on the dashboard and in the Hermes process environment. The dashboard keeps
the receiver route disabled when `YUME_HOOK_TOKEN` is omitted, so the standard
telemetry mode remains fully supported.

```sh
# Generate one token in a shell and copy its printed value.
openssl rand -hex 32
```

Paste that literal value into the dashboard `.env`; dotenv and Compose do not
run shell substitutions. Restart Docker Compose or `make dev` afterward.

```dotenv
YUME_HOOK_TOKEN=replace-with-the-generated-token
```

Use the same literal value in the Hermes process environment:

```sh
export YUME_HOOK_TOKEN="replace-with-the-same-generated-token"

export YUME_HOOK_URL="http://127.0.0.1:8000/api/integrations/hermes/events"
```

For safety, the emitter only accepts an `http://` URL with a literal loopback
IP address (`127.0.0.0/8` or `[::1]`); it rejects hostnames, non-loopback
destinations, URL credentials, and redirects.

Install the emitter and add the printed `subagent_start` and `subagent_stop`
configuration to Hermes yourself:

```sh
./integrations/hermes-hook/install.sh
```

Hermes 0.18.2 approval is per shell-hook command. `hermes hooks test` executes
an already-configured hook but does not create an approval entry. Instead,
start a normal Hermes agent on a TTY and approve only the displayed Yume
observer commands when each hook first runs. For deliberate non-interactive
approval, start that normal agent with `hermes --accept-hooks` or set
`HERMES_ACCEPT_HOOKS=1` for that process.

After both commands are approved, `hermes hooks test` is useful only as a
transport check. Run `doctor` and confirm that both `subagent_start` and
`subagent_stop` observer commands are allowlisted:

```sh
hermes hooks test subagent_start \
  --payload-file integrations/hermes-hook/tests/fixtures/start.json
hermes hooks test subagent_stop \
  --payload-file integrations/hermes-hook/tests/fixtures/stop.json
hermes hooks doctor
```

To remove the opt-in, delete the two hook entries from the Hermes
configuration, revoke the two exact observer commands, remove the installed
emitter, and unset the hook environment variables. Remove `YUME_HOOK_TOKEN`
from the dashboard `.env` and restart the dashboard to disable its receiver
route. Revocation applies to newly started Hermes CLI or gateway processes;
restart the relevant Hermes process because callbacks already registered in a
running process remain active until it restarts.

```sh
hermes hooks revoke "~/.hermes/agent-hooks/yume-observer.py subagent_start"
hermes hooks revoke "~/.hermes/agent-hooks/yume-observer.py subagent_stop"
rm ~/.hermes/agent-hooks/yume-observer.py
unset YUME_HOOK_URL YUME_HOOK_TOKEN
```

## Configuration and assets

`config/dashboard.yaml` selects the asset pack and room rules. Start from
`config/dashboard.example.yaml`. Packs under `asset-packs/` are declarative and
are served read-only at `/asset-packs/{pack-id}/...`; they must preserve the
64×32 tile and 32×48 character-frame contract and contain no executable code.

Startup diagnostics distinguish invalid configuration, invalid assets, and an
unavailable Hermes connection. Fix the reported local input and use the retry
control when Hermes becomes available.

## Repository layout

```text
apps/api/          FastAPI Hermes adapter and backend tests
apps/web/          React/Vite UI and Phaser office renderer
packages/contracts Generated event contracts
asset-packs/       Read-only declarative asset packs
config/            Dashboard configuration
infra/             Docker image definition
tests/fake_hermes  Deterministic Hermes fixture server
tests/e2e/         Playwright browser tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow and
[`docs/release-checklist.md`](docs/release-checklist.md) for the final local
macOS smoke test.
