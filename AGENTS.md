# AGENTS.md

## Cursor Cloud specific instructions

### What this repo is
Invite-only, end-to-end-encrypted messenger MVP (iOS/Android), documented in Russian.
Current state is **specification + engineering artifacts**, not a shipping app:
- Design docs (`*_RU.md`), OpenAPI contract (`openapi/`), PostgreSQL migrations (`db/migrations/`).
- A runnable backend logic prototype in Python/SQLite: `prototype_backend/messenger_service.py`.
There is **no mobile client and no production backend service** yet (only the prototype + docs).

### Where the code lives (non-obvious)
The default branch `main` is empty (only `.gitkeep`). All product code lives on the
`codex/-android-ios` branch (and branches based on it). Make sure you are on a branch that
actually contains the files above before trying to run anything.

### Tooling already available
`python` (3.12, via `python-is-python3`), `rg`, `make`, `psql`, and Docker are pre-installed.
There are **no Python package dependencies** — the prototype and tests use only the standard
library, so there is nothing to `pip install`.

### Run / test / build (no lint or build step exists)
Standard commands are defined in the `Makefile` and `README_RU.md`; prefer those:
- `make validate` — docs / OpenAPI / SQL artifact checks (this is what CI runs). Needs `rg`.
- `make prototype-test` — Python unit tests (`tests/test_messenger_service.py`).
- `make demo-flow` — end-to-end invite → contact → chat → message demo of the core flow.
- `make pg-checks` / `make ci-local` / `scripts/full_local_check.sh` — optional PostgreSQL checks.

Note: the `Makefile` invokes `python` (not `python3`); the `python` alias must exist.

### PostgreSQL checks — gotchas
- Docker is **not running by default**. Start it first: `sudo dockerd &` (then wait a few seconds).
  Your shell needs the `docker` group; either run docker via `sudo`, or use `sg docker -c '...'`
  for a single command (group membership is set but a fresh login is required for it to apply).
- The SQL migrations in `db/migrations/` are **not idempotent**. Re-running `make pg-checks`
  against a database that already has the schema fails with `relation "users" already exists`.
  Wipe the volume between runs with `make pg-reset` (or `docker compose down -v`), or just use
  `scripts/full_local_check.sh` after a reset. PG checks are optional; the prototype/tests need no services.
- `scripts/run_pg_checks.sh` defaults `DATABASE_URL` to the `postgres` db, but the compose service
  and `make pg-checks` use the `messenger_mvp` db (`postgresql://postgres:postgres@localhost:5432/messenger_mvp`).

## Independent ops-control (Пятёрочка / Чижик / ПМ)

Self-contained monitor in `ops_control/`. It SSHes to the four COV hosts and does **not**
depend on those dashboards being up. Secrets stay in `ops_control/.secrets.env` (gitignored).

```bash
make ops-test
make ops-run          # http://127.0.0.1:8787/  Telegram @Crazynewaibot
```

Do not commit SSH keys or bot tokens. Do not deploy X5 scripts onto Chizhik/PM hosts from this window.
Plan: `ops_control/PLAN.md`.
