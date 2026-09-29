# Design: Installation Telemetry

**Date**: 2026-09-29
**Status**: Draft
**Phase**: sdd-design
**Change**: installation-telemetry

## Technical Approach

A new `telemetry` Django app owns one singleton table (`InstallationIdentity`), a pure payload builder, a stdlib HTTP sender, and a background loop. The loop is started explicitly from `config/asgi.py` / `config/wsgi.py` (never from `AppConfig.ready`, so `migrate`, `test` and other management commands never spawn it). Every worker runs the loop; a conditional `UPDATE` on `last_sent_at` guarantees only one worker per 24h window actually sends. The collector is out of scope; this change only produces the v1 wire contract.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Where the loop starts | Explicit `telemetry.runtime.start()` call in `config/asgi.py` and `config/wsgi.py` after the application is built | `AppConfig.ready()`; request middleware | `ready()` runs for every management command (`migrate`, `test`, `shell`), which would send from CI and from one-off commands. Middleware adds per-request cost and must be async-safe under uvicorn workers. The entrypoints run only in real server processes (gunicorn/uvicorn and `runserver`). |
| Scheduling | Daemon thread per process: initial jitter 30-300s, then check every hour | Celery/beat, cron sidecar, compose service | No scheduler exists; adding one for a daily POST is overkill and forces operators to change their compose file. An hourly cheap check with a daily send is enough. Jitter spreads load on the collector after mass restarts. |
| Deduplication | `UPDATE telemetry_installationidentity SET last_sent_at=now WHERE id=1 AND (last_sent_at IS NULL OR last_sent_at < now-24h)`; send only if `rowcount == 1` | Redis lock; `select_for_update` | Atomic in both PostgreSQL and SQLite, works across workers and replicas sharing the DB, no Redis dependency (Redis is optional in Flagward). |
| Claim before send | The slot is claimed first, then the request is made; a failed send is NOT retried until the next window | Claim only on success | Claim-then-send is what makes dedup race-free. Missing one day of data on a failure is acceptable; hammering an unreachable collector from air-gapped installs is not. |
| Identity storage | Singleton row, `id=1` fixed, `installation_id` UUID4, `first_seen_at`, `last_sent_at` | Store in a file under the volume; derive from `SECRET_KEY` | The DB is the only state every install reliably persists. Deriving from secrets would be reversible/correlatable. |
| HTTP client | `urllib.request` with 3s timeout, JSON body, `User-Agent: flagward-telemetry/<version>` | `httpx`, `requests` | `base.txt` has no HTTP client (`httpx` is dev-only). Stdlib keeps the runtime dependency set unchanged. |
| Version source | `config/version.py` `__version__`, overridden by `FLAGWARD_VERSION`; non-semver → `"unknown"` | Docker build arg; git describe at runtime | Operators build images from source through `compose.yml`, so a build arg would usually be empty; `.git` is not guaranteed inside the image. A constant bumped at release is always present. |
| Effective enable | `FLAGWARD_TELEMETRY` explicit value wins; unset/empty → enabled unless `CI` is truthy | Off when `DEBUG=True` (first draft) | The user wants prod vs dev install counts; disabling on `DEBUG` would make the dev count always zero. `CI` is the standard signal set by GitHub Actions and most CI providers. |
| Mode detection | `mode = "development" if settings.DEBUG else "production"`; `server` passed by the caller of `start()`: `asgi.py` → `asgi`, `wsgi.py` → `wsgi` unless `runserver` is in `sys.argv` → `runserver`; `--show`/`--send` → `unknown` | Docker stage marker env; heuristics on hostname | `DEBUG` is what actually separates the two compose files (`compose.yml` False, `compose.dev.yml` True). `server` adds a second, independent signal so misconfigured prod (`DEBUG=False` on `runserver`) is still visible. |
| CI in containers | `compose.dev.yml` backend env adds `CI=${CI:-}`, `FLAGWARD_TELEMETRY=${FLAGWARD_TELEMETRY:-}`, `FLAGWARD_TELEMETRY_URL=${FLAGWARD_TELEMETRY_URL:-}`; `compose.yml` forwards the two telemetry vars | Set `FLAGWARD_TELEMETRY=false` in `ci.yml` only | The e2e job runs `docker compose -f compose.dev.yml up`; runner env vars do not reach containers unless declared. Forwarding `CI` fixes every CI provider at once, not only ours. |
| Tests | `FLAGWARD_TELEMETRY=False` forced in `tests/conftest.py`; sender takes an injectable transport | Mock `urllib` globally | A test run must never reach the network even if someone sets the env var; injection keeps tests explicit. |
| SDK anonymization | `sdk_type` lowercased and checked against `SDKType.values`, else `"other"`; `version` must match a strict semver regex, else `"unknown"`; aggregate by `(type, version)` over `last_seen_at >= now-7d` | Send raw values | `sdk_register` does not validate either field, so both are client-controlled free text. |
| Evaluation volume | `EvaluationLog.objects.filter(timestamp__gte=now-24h).count()` mapped to a bucket | Exact count; add an index on `timestamp` | Bucketed to avoid fingerprinting installs by exact traffic. `timestamp` is not indexed; one scan per day per install is acceptable and adding an index in `sdk_api` would widen this change's blast radius. Revisit if it shows up in slow-query logs. |
| Deployment detection | `docker` if `/.dockerenv` exists, else `bare` | Inspect cgroups | Good enough for an aggregate signal; no false precision needed. |

## Data Flow

```
server process start (asgi.py / wsgi.py)
  → telemetry.runtime.start()
      → is_enabled()? no → return (no thread, no DB access)
      → log INFO "Anonymous telemetry is on. Disable with FLAGWARD_TELEMETRY=false. Details: docs/telemetry.md"
      → start daemon thread:
          sleep(jitter)
          loop every 1h:
            try:
              identity = InstallationIdentity.get_or_create_singleton()
              if not claim_slot(): continue
              payload = build_payload(identity)
              send(payload)                 # 3s timeout
            except DatabaseError: continue  # not migrated yet
            except Exception: log DEBUG     # never propagate
            finally: close_old_connections()
```

`start(server="asgi" | "wsgi")` stores `server` for the process; `build_payload(identity, now, server)` adds `mode` from `DEBUG`.

`manage.py telemetry --show` → `build_payload()` → print JSON (never sends).
`manage.py telemetry --send` → `is_enabled()` check → `build_payload()` → `send()` → print status (ignores the 24h window, still updates `last_sent_at`).

## Module Layout

```
telemetry/
  __init__.py
  apps.py
  models.py            # InstallationIdentity (singleton)
  migrations/0001_initial.py
  settings.py          # is_enabled(), telemetry_url()
  version.py           # get_version()
  payload.py           # build_payload(identity, now) -> dict  (pure, DB reads only)
  anonymize.py         # sdk_type/version mapping, evaluation bucket
  sender.py            # send(payload, transport=urlopen) -> int status
  runtime.py           # start(), claim_slot(), loop
  management/commands/telemetry.py
config/version.py      # __version__ = "0.6.0"
docs/telemetry.md
scripts/telemetry_stub.py   # local collector stub for validation (prints received payloads)
```

## Settings

```python
FLAGWARD_TELEMETRY = os.getenv('FLAGWARD_TELEMETRY')  # None | raw string; resolved by telemetry.settings.is_enabled()
FLAGWARD_TELEMETRY_URL = env_base_url('FLAGWARD_TELEMETRY_URL', 'https://telemetry.flagward.com/v1/heartbeat')
```

The default URL is a placeholder until the collector exists (see Open Questions). The stub makes local validation independent of it.

## Local Validation Plan (Delivery Gate)

1. `python scripts/telemetry_stub.py` → listens on `http://localhost:9999`, prints every JSON body.
2. `FLAGWARD_TELEMETRY=true FLAGWARD_TELEMETRY_URL=http://localhost:9999 python manage.py telemetry --show` → inspect payload by eye.
3. Same env with `--send` → stub prints the payload, command prints `200`.
4. `docker compose up` with those env vars (stub reachable via `host.docker.internal`) → exactly one payload arrives across the 4 gunicorn workers; restart → nothing new within 24h.
5. `FLAGWARD_TELEMETRY=false` → stub receives nothing, no INFO line in logs.
5b. `docker compose -f compose.dev.yml up` with the stub URL → payload arrives with `mode=development`, `server=runserver`; `CI=true docker compose -f compose.dev.yml up` → nothing arrives.
5c. `docker compose up` (prod) → payload arrives with `mode=production`, `server=asgi`.
6. Stop the stub → app logs nothing above DEBUG and keeps serving.

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Unit | `mode`/`server` resolution (DEBUG × entrypoint × runserver argv) | Parametrized |
| Unit | `is_enabled()` truth table incl. `CI`, `get_version()`, sdk anonymization, evaluation buckets | Pure functions, parametrized |
| Unit | Payload key set equals schema v1; no customer strings in serialized payload | Fixtures with recognizable names (`secret-launch`, `Acme`, `ana@acme.com`) |
| Integration | `claim_slot()` returns True once, False inside window; concurrent claims → one winner | DB tests, `last_sent_at` manipulated directly |
| Integration | Kill switch: `start()` creates no thread, no identity row, transport never called | Injected transport spy |
| Integration | Sender swallows timeout/URLError/HTTP 500 | Injected failing transport |
| Integration | Management command `--show` never calls transport; `--send` respects kill switch | `call_command` + spy |

## Open Questions

1. Collector domain/hosting — default URL is a placeholder until decided.
2. First release default-off to validate the pipeline, then flip on? (Decide before release; does not change code shape, only the `is_enabled()` default.)
3. `users` exact vs bucketed — design keeps it exact.
