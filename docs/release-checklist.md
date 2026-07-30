# Local v1 release checklist

This checklist is a host-machine acceptance pass for the macOS-first v1
dashboard. It is intentionally manual where Docker Desktop, native Hermes, and
the browser must be observed together. It is not deployment automation.

## Clean-checkout preflight

- [ ] `git status --short --branch` shows the intended `main` checkout.
- [ ] `git fetch origin` has completed and the local task commit is intended for
      `origin/main`.
- [ ] `uv sync --frozen --all-packages` succeeds.
- [ ] `pnpm install --frozen-lockfile` succeeds.
- [ ] `.env` and `config/dashboard.yaml` exist locally and are ignored.
- [ ] No `.github/workflows/` directory or other CI/CD configuration exists.

## Automated release checks

Run from the repository root:

```bash
make verify
```

This runs `make lint`, `make test`, `make build`, `pnpm e2e`, and builds
`ame-no-uzume:release-candidate` from `infra/docker/Dockerfile`.

For the final clean-checkout gate, also run:

```bash
uv sync --frozen --all-packages
pnpm install --frozen-lockfile
make lint
make test
make build
pnpm e2e
docker build -f infra/docker/Dockerfile -t ame-no-uzume:core-complete .
test ! -d .github/workflows
git status --short
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

The last two commands belong after the focused task commit has been pushed;
they must show no tracked changes and matching local and remote commit IDs.

## Manual macOS smoke test

1. Install Docker Desktop 4.34 or newer and enable **Settings → Resources →
   Network → Enable host networking**.
2. Start native Hermes on `127.0.0.1:8642` with an API key, then start the
   dashboard with `docker compose up --build`.
3. Confirm the dashboard is reachable at
   <http://127.0.0.1:8000> and is not published on a non-loopback interface.
4. Submit one text task. Confirm the persistent Yume session responds and the
   task transcript streams in order.
5. Confirm a scheduled worker appears, a delegated worker enters and leaves,
   and Yume returns to idle after completion.
6. Disconnect Hermes or the dashboard socket. Confirm the UI shows the
   disconnected state, then reconcile to a fresh authoritative snapshot after
   reconnect without inventing workers or actions.
7. Restart only the dashboard container (`docker compose restart dashboard`).
   Confirm the session identifier returned by `/api/bootstrap` is unchanged and
   the dashboard resumes its world state.
8. Confirm the custom asset-pack mount is read-only:

   ```bash
   docker inspect "$(docker compose ps -q dashboard)" \
     --format '{{range .Mounts}}{{if eq .Destination "/asset-packs"}}{{.RW}}{{end}}{{end}}'
   ```

   The command must print `false`.
9. Stop the stack with `docker compose down` and verify no unexpected process
   remains listening on the dashboard port.

## Sign-off

Record the date, macOS version, Docker Desktop version, Hermes version, and the
commit tested. Release v1 locally only when every automated and manual item is
checked and the worktree is clean.
