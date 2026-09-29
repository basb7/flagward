# Proposal: Installation Telemetry

**Date**: 2026-09-29
**Status**: Draft
**Phase**: sdd-proposal
**Change**: installation-telemetry

## Intent

Flagward is self-hosted, so today we are blind: we do not know how many installations exist, which versions they run, whether multivariate flags or segment rollouts are used, or which SDK adapters (React, Vue, Svelte, Solid) matter. This change adds an **anonymous, aggregate-only, opt-out** daily heartbeat from each installation to a Flagward-owned collector, so roadmap and support decisions are based on real usage instead of guesses.

## Principles (non-negotiable)

1. **Anonymous**: no emails, names, IPs stored by us, domains, hostnames, flag keys/names, segment values, user context or API keys. Ever.
2. **Aggregate-only**: counts, booleans, enums and versions. No per-row data.
3. **Opt-out with one variable**: `FLAGWARD_TELEMETRY=false` disables everything, including the network call.
4. **Transparent**: every field is documented publicly; the server logs once at startup that telemetry is on and how to disable it.
5. **Never harmful**: telemetry failures never raise, never block requests, never slow startup. Short timeout, fire-and-forget.

## Scope

### In Scope

- `telemetry` Django app in this repo (the **sender**)
- `InstallationIdentity` singleton: random UUID `installation_id` + `first_seen_at` + `last_sent_at`, created on first run
- Single application version source (`config/version.py` constant bumped at release, optional `FLAGWARD_VERSION` env override, `unknown` otherwise)
- Payload builder with a versioned schema (`schema_version: 1`) — see Payload below
- Daily heartbeat trigger that works without a scheduler and is deduplicated across workers
- `manage.py telemetry --show` command that prints the exact JSON that would be sent (no network)
- Settings: `FLAGWARD_TELEMETRY` (default `true`), `FLAGWARD_TELEMETRY_URL` (default Flagward collector)
- Enabled by default in both production and development installs; payload reports `mode` (`production` | `development`) and `server` (`asgi` | `wsgi` | `runserver`) so prod and dev installs can be counted separately
- Automatic disable in tests and in CI (`CI` env var truthy) unless explicitly enabled; `compose.dev.yml` forwards `CI` into the backend container
- Docs: `docs/telemetry.md` (field list, rationale, how to disable) + README section
- Unit + integration tests (payload has no forbidden fields, kill switch prevents any HTTP call, failures are swallowed, dedup works)

### Out of Scope

- **The collector service itself** (ingestion endpoint, storage, dashboards) — separate repo/change; this change only defines the wire contract it must accept
- Dashboard UI to view or toggle telemetry (possible follow-up)
- Telemetry from the JS SDKs (`flagward-sdk-js`) — installations already report SDK inventory through `SDKRegistration`
- Product analytics inside the dashboard (clicks, page views, session replay)
- Error/crash reporting (Sentry-style)

## Payload (schema_version 1)

```json
{
  "schema_version": 1,
  "installation_id": "random-uuid-v4",
  "sent_at": "2026-09-29T12:00:00Z",
  "first_seen_at": "2026-08-01T09:30:00Z",
  "flagward_version": "0.6.0",
  "mode": "production | development",
  "server": "asgi | wsgi | runserver",
  "runtime": {
    "python": "3.14",
    "django": "6.1",
    "deployment": "docker | bare",
    "database": "postgresql | sqlite",
    "redis_enabled": true,
    "email_configured": true,
    "default_plan": "COMMUNITY"
  },
  "usage": {
    "organizations": 2,
    "projects": 5,
    "environments": 12,
    "users": 18,
    "flags": { "total": 140, "boolean": 120, "multivariate": 20 },
    "flags_with_rules": 35,
    "strategy_rules": 60,
    "rules_with_rollout": 22,
    "variants": 55,
    "active_overrides": 3
  },
  "sdks": [
    { "type": "react", "version": "0.4.0", "active_7d": 4 },
    { "type": "other", "version": "unknown", "active_7d": 1 }
  ],
  "evaluations_24h_bucket": "1k-10k"
}
```

Notes:
- `sdks[].type` is mapped against the `SDKType` allowlist; anything else becomes `other`. `version` must match semver or becomes `unknown` (the stored values are client-controlled free text).
- `mode` is `development` when `DEBUG=True`, `production` otherwise. `server` tells a real server from a local `runserver`, so a production-mode install running `runserver` is still recognizable.
- Evaluation volume is sent as a bucket (`0`, `1-100`, `100-1k`, `1k-10k`, `10k-100k`, `100k+`), not an exact number.
- The collector receives the request IP by nature of HTTP; the collector contract states it MUST NOT persist it.

## Capabilities

### New Capabilities

- `installation-telemetry`: identity, payload contract, trigger, opt-out, transparency

### Modified Capabilities

None — reads existing models without changing them.

## Approach

1. **Identity**: `InstallationIdentity` singleton model with a data-migration-free `get_or_create` on first use. Random UUID, never derived from secrets or host data.
2. **Version**: `config/version.py` holds `__version__`, bumped as part of each release (users build images from source via `compose.yml`, so a Docker build arg would usually be empty). `FLAGWARD_VERSION` env var overrides it when set.
3. **Trigger**: on process start (`AppConfig.ready`) and lazily on requests (cheap cached check), if `last_sent_at` is older than 24h, atomically claim the slot (conditional `UPDATE ... WHERE last_sent_at < now-24h`) and send in a daemon thread. The conditional update is the dedup across Gunicorn workers and replicas sharing one database. Exact mechanism confirmed in design.
4. **Send**: `POST` JSON to `FLAGWARD_TELEMETRY_URL`, 3s timeout, no retries, all exceptions caught and logged at `DEBUG`.
5. **Kill switch**: when `FLAGWARD_TELEMETRY=false`, no identity row is created, no thread starts, no network call happens.
6. **Transparency**: startup `INFO` log line + `manage.py telemetry --show` + `docs/telemetry.md`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `telemetry/` | New | App: model, payload builder, sender, trigger, management command |
| `config/settings.py` | Modified | `INSTALLED_APPS`, `FLAGWARD_TELEMETRY`, `FLAGWARD_TELEMETRY_URL`, `FLAGWARD_VERSION` |
| `config/version.py` | New | Single `__version__` source, bumped at release |
| `config/asgi.py`, `config/wsgi.py` | Modified | Start the telemetry loop in server processes only |
| `compose.yml` | Modified | Forward `FLAGWARD_TELEMETRY` / `FLAGWARD_TELEMETRY_URL` from `.env` |
| `compose.dev.yml` | Modified | Forward `CI`, `FLAGWARD_TELEMETRY`, `FLAGWARD_TELEMETRY_URL` so CI runs stay silent |
| `README.md`, `docs/telemetry.md` | Modified/New | Public field list and opt-out instructions |
| `tests/` | New | Payload, privacy, kill switch, dedup, failure tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Community backlash for default-on telemetry | Medium | Anonymous + aggregate only, public field list, one-variable opt-out, startup log, `--show` command |
| Accidental PII leak through free-text fields | Medium | Allowlist/semver mapping; test asserting no field outside the schema and no flag keys/emails in payload |
| Duplicate heartbeats from multiple workers/replicas | High | Conditional DB update claims the daily slot; collector also dedups by `(installation_id, day)` |
| Telemetry slows or breaks the app | Low | Daemon thread, 3s timeout, all exceptions swallowed, never in request path |
| Air-gapped installs log noisy errors | Medium | Failures logged at `DEBUG` only |
| CI or contributors' throwaway DBs inflate dev counts | High | `CI` disables by default; collector reports dev installs as "active in last N days", not all-time IDs; `first_seen_at` separates one-off runs |
| Cloned DB/volume duplicates `installation_id` | Low | Accept; `first_seen_at` + collector heuristics; documented |
| Count queries expensive on big installs | Low | Runs once per day, simple `COUNT`s; evaluations use indexed `created_at` range |

## Rollback Plan

Set `FLAGWARD_TELEMETRY=false` on any install to stop immediately. Code rollback: revert the change; the `telemetry` app owns only its own table, so its migration can be reversed without touching other data.

## Dependencies

- A reachable collector endpoint accepting `schema_version: 1` before this ships enabled by default (separate change). Until then, the default URL can point to a stub or the feature ships behind `FLAGWARD_TELEMETRY` defaulting to `false` for one release.

## Delivery Gate

No commit and no release for this change until the user has approved it and validated it locally (heartbeat reaching a local collector stub, kill switch, `--show` output, dedup across workers).

## Success Criteria

- [ ] A fresh install sends exactly one heartbeat per 24h regardless of worker count
- [ ] `FLAGWARD_TELEMETRY=false` produces zero outbound requests (verified by test)
- [ ] `manage.py telemetry --show` prints the exact payload
- [ ] Payload contains only schema fields; privacy test fails on any new unapproved field
- [ ] Collector unreachable → app behaves identically, no errors above `DEBUG`
- [ ] `docs/telemetry.md` lists every field and how to disable it

## Open Questions

1. Collector domain and hosting (e.g. `telemetry.flagward.com`) — needed for the default URL.
2. Should the first release ship default-off (to validate the pipeline) and flip to default-on in the next?
3. Is `users` count acceptable as exact, or should it also be bucketed?
