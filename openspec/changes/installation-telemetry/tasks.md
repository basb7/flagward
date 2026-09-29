# Tasks: Installation Telemetry

**Date**: 2026-09-29
**Status**: Draft
**Phase**: sdd-tasks
**Change**: installation-telemetry

## Delivery Gate

No commit and no release until the user approves and validates locally (Phase 6). Implementation happens in the working tree only.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 800-1100 (≈45% tests) |
| 400-line budget risk | High |
| Chained PRs recommended | Optional |
| Suggested split | PR 1: identity + payload + `--show` (no network) → PR 2: sender + runtime loop + compose + docs |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before commit: Yes (single PR vs 2-PR chain)
Chained PRs recommended: Optional
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | App skeleton, enable rules, version, identity, anonymization, payload, `--show` | PR 1 | `pytest tests/unit/test_telemetry_*.py tests/integration/test_telemetry_payload.py` | pytest | `telemetry/`, `config/version.py`, `config/settings.py` |
| 2 | Sender, dedup claim, runtime loop, entrypoints, `--send`, compose, stub, docs | PR 2 | `pytest tests/integration/test_telemetry_runtime.py` | pytest + local stub | `telemetry/sender.py`, `telemetry/runtime.py`, `config/asgi.py`, `config/wsgi.py`, compose files |

## Phase 1: Foundation

- [x] 1.1 Create `telemetry` app (`apps.py`, `__init__.py`), add to `INSTALLED_APPS` in `config/settings.py`
- [x] 1.2 Add `FLAGWARD_TELEMETRY` (raw, may be None) and `FLAGWARD_TELEMETRY_URL` (`env_base_url`, placeholder default) to `config/settings.py`
- [x] 1.3 Force `FLAGWARD_TELEMETRY="false"` for the test suite in `tests/conftest.py`
- [x] 1.4 RED: `is_enabled()` truth table — explicit truthy/falsy wins; unset/empty → enabled unless `CI` truthy; `DEBUG` has no effect
- [x] 1.5 GREEN: `telemetry/settings.py` `is_enabled()`, `telemetry_url()`
- [x] 1.6 Add `config/version.py` with `__version__ = "0.6.0"`
- [x] 1.7 RED: `get_version()` — returns `__version__`; `FLAGWARD_VERSION` overrides; non-semver/empty → `"unknown"`
- [x] 1.8 GREEN: `telemetry/version.py`

## Phase 2: Identity

- [x] 2.1 RED: `InstallationIdentity.get_or_create_singleton()` creates one row with UUID4 and `first_seen_at`; second call returns the same row
- [x] 2.2 GREEN: `telemetry/models.py` (fixed `id=1`, `installation_id`, `first_seen_at`, `last_sent_at` nullable)
- [x] 2.3 `python manage.py makemigrations telemetry`; verify `migrate` and reverse migration run cleanly

## Phase 3: Payload

- [x] 3.1 RED: SDK anonymization — unknown `sdk_type` → `"other"`, case-insensitive match against `SDKType.values`, non-semver version → `"unknown"`
- [x] 3.2 RED: evaluation bucket boundaries (`0`, `1-100`, `100-1k`, `1k-10k`, `10k-100k`, `100k+`), incl. edges 0, 1, 100, 1000
- [x] 3.3 GREEN: `telemetry/anonymize.py`
- [x] 3.4 RED: `mode`/`server` — `DEBUG` → development/production; `server` argument kept as given; default `"unknown"`
- [x] 3.5 RED: payload key set (recursive) equals schema v1 exactly
- [x] 3.6 RED: usage counts — orgs, projects, environments, users, flags by type, flags_with_rules, strategy_rules, rules_with_rollout, variants, active_overrides
- [x] 3.7 RED: SDKs aggregated by `(type, version)` with `active_7d` counting only `last_seen_at >= now-7d`
- [x] 3.8 RED: privacy — fixtures with flag `secret-launch`, org `Acme`, user `ana@acme.com`, variant `treatment-x`; serialized payload contains none of them
- [x] 3.9 RED: runtime block — python/django versions, deployment (`/.dockerenv`), database vendor, redis_enabled, email_configured, default_plan
- [x] 3.10 GREEN: `telemetry/payload.py` `build_payload(identity, now, server="unknown")`
- [x] 3.11 RED: `manage.py telemetry --show` prints valid JSON and never calls the transport
- [x] 3.12 GREEN: `telemetry/management/commands/telemetry.py` (`--show` only)

## Phase 4: Sender and Runtime

- [x] 4.1 RED: `send()` posts JSON with `Content-Type` and `User-Agent: flagward-telemetry/<version>`, 3s timeout, returns status
- [x] 4.2 RED: `send()` swallows `URLError`, timeout, HTTP 500; logs at `DEBUG` only
- [x] 4.3 GREEN: `telemetry/sender.py` with injectable transport (default `urllib.request.urlopen`)
- [x] 4.4 RED: `claim_slot()` — True when `last_sent_at` NULL or older than 24h and stamps it; False inside window; two consecutive claims → one True
- [x] 4.5 GREEN: `claim_slot()` via conditional `UPDATE` in `telemetry/runtime.py`
- [x] 4.6 RED: `run_once()` — claim → build → send; claim lost → no send; `DatabaseError` (table missing) → skipped silently; send failure does not unclaim
- [x] 4.7 RED: `start()` with telemetry disabled → no thread, no identity row, transport never called, no INFO log
- [x] 4.8 RED: `start()` enabled → one INFO line with the disable instruction; daemon thread started once per process (idempotent)
- [x] 4.9 GREEN: `start(server)`, `run_once()`, loop (jitter 30-300s, hourly, `close_old_connections()`)
- [x] 4.10 Call `telemetry.runtime.start(server="asgi")` in `config/asgi.py` and `start(server="runserver" if "runserver" in sys.argv else "wsgi")` in `config/wsgi.py`
- [x] 4.11 RED: `--send` respects kill switch; when enabled sends ignoring the window, updates `last_sent_at`, prints status or error
- [x] 4.12 GREEN: `--send` in the management command

## Phase 5: Configuration and Docs

- [x] 5.1 `compose.dev.yml` backend env: `CI=${CI:-}`, `FLAGWARD_TELEMETRY=${FLAGWARD_TELEMETRY:-}`, `FLAGWARD_TELEMETRY_URL=${FLAGWARD_TELEMETRY_URL:-}` with a short comment
- [x] 5.2 `compose.yml` backend env: `FLAGWARD_TELEMETRY=${FLAGWARD_TELEMETRY:-}`, `FLAGWARD_TELEMETRY_URL=${FLAGWARD_TELEMETRY_URL:-}`
- [x] 5.3 `.env.example`: commented `FLAGWARD_TELEMETRY` / `FLAGWARD_TELEMETRY_URL` entries
- [x] 5.4 `scripts/telemetry_stub.py`: stdlib HTTP server on `:9999`, prints each JSON body, returns 204
- [x] 5.5 `docs/telemetry.md`: every field, what is never sent, how to disable, `--show`, note for running `compose.yml` inside a CI
- [x] 5.6 README: short Telemetry section linking `docs/telemetry.md`
- [x] 5.7 Quality: `ruff check .`, `ruff format --check .`, full `pytest`

## Phase 6: Local Validation (user)

- [x] 6.1 Run the stub; `--show` with stub URL → review payload
- [x] 6.2 `--send` → stub prints payload, command prints status
- [x] 6.3 `docker compose -f compose.dev.yml up` → one payload, `mode=development`, `server=runserver`
- [ ] 6.4 `CI=true docker compose -f compose.dev.yml up` → nothing arrives
- [x] 6.5 `docker compose up` (prod, 4 workers) → exactly one payload, `mode=production`, `server=asgi`; restart → nothing new within 24h
- [x] 6.6 `FLAGWARD_TELEMETRY=false` → nothing arrives, no INFO line
- [x] 6.7 Stop the stub → app keeps serving, no log above DEBUG
- [x] 6.8 User approves → then decide commit/PR split
