# Exploration: Installation Telemetry

**Date**: 2026-09-29
**Change**: installation-telemetry

## Question

How can we learn how self-hosted Flagward installations are actually used (how many exist, which versions run, which features and SDKs get adopted) without collecting personal or customer data?

## Current State

- Flagward is self-hostable via `docker compose up`; there is no way to know how many installations exist or what they run.
- No background scheduler: no Celery, no cron, no beat. Work only happens inside request/response cycles or management commands.
- Configuration is env-driven through helpers in `config/settings.py` (`env_bool`, `env_list`, `env_url`).
- There is no single application version source: `frontend/package.json` says `0.1.0`, `pyproject.toml` has none, releases are git tags (`v0.6.0`).
- Useful data already exists locally:
  - `tenancy.Organization`, `tenancy.Project`, `core_flags.Environment`, Django users
  - `core_flags.FeatureFlag` (`flag_type`: BOOLEAN / MULTIVARIATE), `Variant`, `StrategyRule`, `Condition`, `FlagOverride`
  - `sdk_api.SDKRegistration` (`sdk_type`, `version`, `last_seen_at`)
  - `sdk_api.EvaluationLog` (per-evaluation rows)
- `sdk_register` does not validate `sdk_type` against `SDKType`, so the stored value is client-controlled free text.

## Findings

1. **Identity**: we need a stable, random installation ID. Deriving it from `SECRET_KEY`, hostname or domain would leak or correlate data; a random UUID persisted in the database is the safe choice.
2. **Scheduling**: without a scheduler, a daily heartbeat must be triggered lazily (e.g. checked on request or at process start, deduplicated through the database/cache) or via a management command. Multiple Gunicorn workers mean the send must be guarded against duplicates.
3. **Versioning**: telemetry is useless without a reliable version. A single version source must be introduced (build arg baked into the image, falling back to package metadata).
4. **Free-text leakage risk**: `SDKRegistration.sdk_type` and `version` are client-supplied. Telemetry must map them against an allowlist (unknown → `other`) and validate version as semver before sending.
5. **Precedent**: Next.js, PostHog, Flagsmith and Unleash all ship anonymous opt-out telemetry for self-hosted installs, disabled with one env var and documented publicly.

## Recommendation

Opt-out, anonymous, aggregate-only daily heartbeat sent to a Flagward-owned collector, with a strict versioned payload schema, a one-variable kill switch, and a public document listing every field.
