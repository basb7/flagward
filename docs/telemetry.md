# Telemetry

Flagward sends anonymous, aggregate usage data once a day so maintainers know how many installations exist, which versions they run, and which features and SDKs are used. This page lists every field it sends and how to turn it off.

## TL;DR

- **Turn it off**: set `FLAGWARD_TELEMETRY=false` in your `.env` (or environment) and restart.
- **See what is sent**: `python manage.py telemetry --show` prints the exact payload. Nothing is sent.
- **What is sent**: counts, booleans, enums and version numbers. Nothing that identifies you, your users or your flags.

## What is never sent

- Emails, usernames, names of organizations, projects, environments, flags or variants
- Flag keys, condition values, evaluation contexts, user IDs
- API keys, `SECRET_KEY`, hostnames, domains, IP addresses
- Any free text: SDK names and versions reported by clients are mapped to a fixed list (`other` / `unknown` otherwise)

The collector necessarily sees the IP address of the HTTP request; it does not store it.

## When it is on

| `FLAGWARD_TELEMETRY` | `CI` | Telemetry |
|----------------------|------|-----------|
| unset or empty | unset | **on** |
| unset or empty | `true` | off |
| `true` / `1` / `yes` / `on` | any | on |
| `false` / `0` / `no` / `off` | any | off |
| anything else | any | off |

`DEBUG` does not turn it on or off; it only sets the reported `mode`. Both production and development installs are counted, separately.

When it is on, the server logs this once per process at startup:

```
Anonymous telemetry is on. Disable it with FLAGWARD_TELEMETRY=false. See docs/telemetry.md for exactly what is sent.
```

`compose.dev.yml` forwards `CI` into the backend container, so CI pipelines stay silent. If you run `compose.yml` inside your own CI, set `FLAGWARD_TELEMETRY=false` there.

## How it works

- A random ID (UUID v4) is created in the database the first time telemetry runs. It is not derived from anything on your machine. Deleting the database creates a new one.
- Each server process checks once an hour. Only one send per installation happens per 24 hours, even with several workers or replicas sharing a database.
- The request has a 3-second timeout, is never retried, and never blocks or breaks the application. Failures are logged at `DEBUG` only, so air-gapped installs stay quiet.
- `FLAGWARD_TELEMETRY=false` means no thread, no database row and no network request at all.

## Fields (schema version 1)

| Field | Example | Meaning |
|-------|---------|---------|
| `schema_version` | `1` | Payload format version |
| `installation_id` | `"5ab8…63e6"` | Random ID of this installation |
| `sent_at` | ISO 8601 | When this payload was built |
| `first_seen_at` | ISO 8601 | When telemetry first ran on this installation |
| `flagward_version` | `"0.6.0"` | Flagward version (`unknown` if not semver) |
| `mode` | `"production"` | `development` when `DEBUG=True`, else `production` |
| `server` | `"asgi"` | `asgi`, `wsgi`, `runserver`, or `unknown` (management commands) |
| `runtime.python` | `"3.14"` | Python major.minor |
| `runtime.django` | `"6.1"` | Django major.minor |
| `runtime.deployment` | `"docker"` | `docker` or `bare` |
| `runtime.database` | `"postgresql"` | `postgresql` or `sqlite` |
| `runtime.redis_enabled` | `true` | Redis cache configured |
| `runtime.email_configured` | `false` | `EMAIL_HOST` set |
| `runtime.default_plan` | `"COMMUNITY"` | Plan for new organizations (`other` if unrecognized) |
| `usage.organizations` | `2` | Count |
| `usage.projects` | `5` | Count |
| `usage.environments` | `12` | Count |
| `usage.users` | `18` | Active users |
| `usage.flags.total` / `.boolean` / `.multivariate` | `140` / `120` / `20` | Flags by type |
| `usage.flags_with_rules` | `35` | Flags with at least one strategy rule |
| `usage.strategy_rules` | `60` | Count |
| `usage.rules_with_rollout` | `22` | Rules targeting a variant |
| `usage.variants` | `55` | Count |
| `usage.active_overrides` | `3` | Kill-switch overrides currently active |
| `sdks[].type` | `"react"` | SDK type from a fixed list, else `other` |
| `sdks[].version` | `"0.4.0"` | SDK version if semver, else `unknown` |
| `sdks[].active_7d` | `4` | **Environments** where this SDK type and version was seen in the last 7 days (not apps or end users) |
| `evaluations_24h_bucket` | `"1k-10k"` | Flag evaluations in the last 24 h, as a range: `0`, `1-100`, `100-1k`, `1k-10k`, `10k-100k`, `100k+` (lower bound inclusive) |

Any change to this list bumps `schema_version` and is documented here first.

## Inspecting it locally

```bash
# 1. Start a local collector that prints what it receives
python scripts/telemetry_stub.py

# 2. In another terminal, preview and send
FLAGWARD_TELEMETRY=true FLAGWARD_TELEMETRY_URL=http://localhost:9999 python manage.py telemetry --show
FLAGWARD_TELEMETRY=true FLAGWARD_TELEMETRY_URL=http://localhost:9999 python manage.py telemetry --send
```

From a compose container use `FLAGWARD_TELEMETRY_URL=http://host.docker.internal:9999` (on Linux, add `extra_hosts: ["host.docker.internal:host-gateway"]` to the backend service).

`--send` sends immediately, ignoring the 24-hour window, and counts as that day's heartbeat.
