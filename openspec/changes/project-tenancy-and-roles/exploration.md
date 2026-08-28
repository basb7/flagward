# Exploration: Project-Level Multi-Tenancy with Role-Based Permissions

**Date**: 2026-08-28
**Phase**: sdd-explore
**Change**: project-tenancy-and-roles
**Artifact store**: hybrid (Engram topic `sdd/project-tenancy-and-roles/explore`, id 456)

## Current State

No tenant isolation exists. `EnvironmentViewSet.queryset = Environment.objects.all()`
(`core_flags/api/views.py:30`) has no `get_queryset` and no per-view `permission_classes`.
The global `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` (`config/settings.py:187-189`)
is the only gate. Any authenticated `auth.User` can read and write every `Environment`,
`FeatureFlag`, `StrategyRule`, `Condition` and `FlagOverride` in the database.

There is no custom `AUTH_USER_MODEL`; `authentication/models.py` is empty.

`Environment.Meta.unique_together = ("key",)` (`core_flags/models.py:40`) is global.
`Environment.api_key` is a separate `unique=True` field (`core_flags/models.py:37`),
independent of `unique_together`, and is the SDK's sole resolution key
(`sdk_api/authentication.py:25`, `sdk_api/views.py:147`).

## Affected Surfaces

### `core_flags/api/views.py`

| Symbol | Lines | Gap |
|---|---|---|
| `EnvironmentViewSet` | 28-31 | Unscoped queryset, no permission class |
| `FeatureFlagViewSet` | 34-47 | Unscoped; `filter_fields = ("environment", ...)` lets any user pass any environment id through `QueryParamFilterMixin` (`core/api/mixins.py:51-64`) and read another tenant's flags |
| `StrategyRuleViewSet` | 50-54 | Fully unscoped |
| `ConditionViewSet` | 57-61 | Fully unscoped |
| `FlagOverrideViewSet` | 64-121 | Unscoped; `perform_create` (106-114) reads `validated_data["flag"]` with no ownership check |

### `core_flags/api/serializers.py` — the FK-narrowing hole

`FeatureFlagSerializer.environment` (implicit `PrimaryKeyRelatedField`, 49-69) defaults to
`Environment.objects.all()`. A POST/PATCH can attach a flag to ANY environment id, including
another tenant's, even when list/retrieve is correctly scoped. The same hole exists one level
down in `StrategyRuleSerializer.flag` (31-38), `ConditionSerializer.rule` (23-28) and
`FlagOverrideSerializer.flag` (94-126).

A serializer's related-field queryset is independent of the view's `get_queryset`. Scoping the
view does not close this. This confirms that queryset scoping and serializer FK narrowing are
two distinct required layers, not redundant ones.

### `analytics/` — the most severe leak found

`build_overview` (`analytics/services.py:58-151`), `build_evaluations_timeseries` (154-204),
`build_top_flags` (207-248) and `build_sdk_health` (251-300) all take an optional
`environment_id`. `_scope_by_environment` (44-48) is a no-op when it is `None`, so the default
path aggregates **globally across all tenants**.

`analytics/api/views.py:14-51` parses `environment_id` from an optional query param and never
requires it, and performs no ownership check even when one IS supplied. Any authenticated user
can pass any other tenant's environment UUID and receive their real analytics.

### `sdk_api/api/views.py` (dashboard-facing)

`SDKRegistrationViewSet` (15-22) and `EvaluationLogViewSet` (25-35): unscoped querysets, same
class of leak.

### `core_flags/admin.py`

Django admin is a separate, staff/superuser-gated surface. Needs `Project` and
`ProjectMembership` registered, and optionally a `project` column on `EnvironmentAdmin`.

## `.distinct()` Analysis — NOT needed

Every affected model reaches `Environment` through a straight-line FK chain, never M2M:
`FeatureFlag.environment` (`models.py:54`), `StrategyRule.flag` (76), `Condition.rule` (94),
`FlagOverride.flag` (130), `EvaluationLog.flag` (`sdk_api/models.py:56`),
`SDKRegistration.environment` (`sdk_api/models.py:21`).

With `Environment.project` as a single FK and `ProjectMembership.Meta.unique_together =
("project", "user")`, a filter such as `environment__project__memberships__user=request.user`
matches at most one membership row per (project, user), and each base row reaches exactly one
project. The join cannot fan out. `.distinct()` would be cargo cult here.

**This invariant depends on the uniqueness constraint.** If a future role model ever allows
multiple membership rows per (project, user) — e.g. several simultaneous roles — the invariant
breaks and `.distinct()` becomes necessary.

## SDK Blast Radius — zero code changes required

- `SDKAuthentication.authenticate` (`sdk_api/authentication.py:18-31`) depends only on
  `api_key`'s own field-level `unique=True`, untouched by moving `Meta.unique_together`.
- `serialize_environment_flags` / `serialize_flag` / `active_overrides_by_flag`
  (`sdk_api/payloads.py:11-81`) operate on an already-resolved `Environment`.
- `sdk_stream` SSE (`sdk_api/views.py:128-212`) resolves by `api_key` at line 147.
- `core_flags/notifications.py:21-23` keys the Redis channel purely on `environment.id`.
- `SDKRegistration.Meta.constraints` on `(environment, sdk_type)` is unaffected.

**Hard constraint for the design phase**: `Environment.api_key` must keep `unique=True` and
must never become tenant-scoped. That is what makes this a zero-breaking-change path for
existing SDK consumers.

## Bootstrap and Seed Data

No fixtures directory exists. The single custom management command,
`core/management/commands/create_super_user.py`, idempotently creates a Django superuser from
env vars and creates **no project membership**.

`compose.yml:60-63` and `compose.dev.yml:66-67` run, on every container start:
`migrate && create_super_user && gunicorn ...`. Migrations run BEFORE the superuser exists, so
an ownership-backfill migration must never depend on that command having already run.

## Production Data Migration — matcherclub.com

The deploy pipeline runs `migrate` automatically and non-interactively on every restart. Every
step must be automatic and idempotent.

1. **Additive schema migration** — create `projects` app with `Project`, `ProjectMembership`.
   No existing table touched.
2. **Add `Environment.project` as NULLABLE.** It cannot be added NOT NULL in one step against a
   populated table without Django prompting for a one-off default, which is impossible in a
   non-interactive `migrate`. Nullable-first is mandatory.
3. **`RunPython` backfill** — attach every `Environment` with `project_id IS NULL` to a project
   and create OWNER memberships. **UNRESOLVED**: `Environment` has no `created_by` or audit
   field, so there is no data-driven way to decide who owns which pre-existing environment.
   This is a business decision (see Open Questions).
4. **Alter `Environment.project` to NOT NULL** — safe once step 3 is unconditional and complete.
5. **Change `Meta.unique_together`** from `("key",)` to `("project", "key")` — strictly widens
   what is allowed, so no existing row can violate it. Low risk.
6. **Rollback gap** — the step 3 ownership assignment has no clean reverse once real users
   depend on their assigned membership.

## CI vs Production Database Engine — CONFIRMED GAP

`config/settings.py:94` selects Postgres only when `DB_NAME` or `USE_POSTGRES` is set, and falls
back to SQLite otherwise. `.github/workflows/ci.yml` defines no service container and no database
environment variables for the `Backend (lint + tests)` job.

**CI therefore runs on SQLite while production runs on Postgres.** SQLite alters constraints by
rebuilding the table; Postgres issues `ALTER`. A green CI run does not prove the NOT NULL and
`unique_together` migrations behave correctly against production. The design phase must decide
whether to add a Postgres service to CI or to verify the migration separately.

## Test Suite Exposure

170 tests. **No `conftest.py` exists anywhere in the repository** — there is no shared factory or
fixture layer. Every file builds its own objects inline.

11 of 12 test files call `Environment.objects.create(...)` and/or `FeatureFlag.objects.create(...)`
directly — 126 call sites:

| File | Sites |
|---|---|
| `tests/unit/test_models.py` | 40 |
| `tests/integration/test_monitoring_api.py` | 19 |
| `tests/integration/test_analytics_api.py` | 18 |
| `tests/unit/test_evaluation.py` | 16 |
| `tests/integration/test_admin_api.py` | 9 |
| `tests/integration/test_sdk_override_payload.py` | 8 |
| `tests/integration/test_sdk_api.py` | 6 |
| `tests/unit/test_override_precedence.py` | 5 |
| `tests/unit/test_flag_notifications.py` | 2 |
| `tests/unit/test_sdk_registration.py` | 2 |
| `tests/integration/test_sse.py` | 1 |

Once `Environment.project` is NOT NULL, every one of these breaks at setup time.

`tests/integration/test_admin_api.py:27-127` bodies are stub `pass` statements with
`force_authenticate(user=None)` and `# TODO: Implement admin authentication`. They assert nothing
today but still create rows in `setup_method`, so they add diff noise without providing coverage.

Recommendation: introduce a shared `conftest.py` with `project`/`environment` factory fixtures as
an explicit early step. This is new test infrastructure and must be counted in the estimate, not
treated as free.

## Frontend Surface

`frontend/src/lib/api.ts`: `environmentsApi.list()` (206-209) and `flagsApi.list()` (269-270) have
no project filter. `analyticsApi.*` (536-558) already threads an optional `environment?: string`
through `buildQuery`, so extending that family with `project?: string` follows an established
pattern.

Six dashboard files are touched: `layout.tsx`, `environments/page.tsx`, `flags/page.tsx`,
`flags/[id]/rules/page.tsx`, `monitoring/page.tsx`, `page.tsx`. No project-switcher component was
found among the files read (not exhaustively grepped, so "not found", not "confirmed absent").

**Recommend the `?project=` query-param approach.** Nested routes (`/dashboard/[projectId]/...`)
would require moving every page one level down in the App Router tree and rewriting every internal
`Link` and `router.push`, for no benefit over the flat structure already in place.

## Line Estimate

| Bucket | Lines |
|---|---|
| Backend (projects app, capability map, permission class, viewset + serializer scoping across `core_flags/api/`, `sdk_api/api/`, `analytics/api/`) | 450-650 |
| Migrations (schema, nullable FK, RunPython backfill, NOT NULL + unique_together) | 80-150 |
| Tests (11 file migrations, new `conftest.py`, new scoping/permission tests) | 300-500 |
| Frontend (`api.ts`, project context + switcher, 6 page wirings) | 200-300 |
| **Total** | **~1050-1600** |

This exceeds the 800-line session review budget and must be sliced.

## Proposed Slicing

1. **PR1 — `projects` app schema.** Models, migrations, admin registration, capability map.
   Purely additive, no behavior change. ~150-250 lines.
2. **PR2 — Data migration.** Nullable `Environment.project` + `RunPython` backfill with the
   documented ownership decision. Still nullable, so nothing breaks yet. Isolates the highest-risk,
   least-reversible step into its own revertable unit. ~80-150 lines.
3. **PR3 — Enforcement.** NOT NULL + `unique_together`, queryset scoping, serializer FK narrowing,
   `HasProjectCapability`, plus the full test-suite migration. Largest slice; likely needs a
   further split (3a backend enforcement, 3b test infrastructure) to respect the budget.
4. **PR4 — Frontend.** Project selector, `api.ts`, dashboard wiring. Independent once PR3's API
   contract is stable.

## Open Questions for sdd-propose

1. **Who owns matcherclub.com's existing environments?** No ownership signal exists in the data.
   Options: (a) one shared "Legacy" project with every existing `auth.User` as OWNER — broad but
   nobody loses access; (b) attach only to the bootstrap superuser and re-invite everyone else —
   likely wrong if multiple real dashboard users exist. Must be decided explicitly; no clean
   rollback once assigned.
2. **Does the Django superuser bypass `HasProjectCapability`?** `create_super_user` creates no
   membership, so the bootstrap account would be locked out of every scoped endpoint. Options:
   special-case `is_superuser` in the permission class, or auto-provision a membership.
3. **What happens on self-registration?** `authentication/views.py:105-160` lets anyone register a
   plain `auth.User` with no project step. Auto-create a personal project, require an invite, or
   leave the user project-less until invited?
4. **Does CI gain a Postgres service** so migration behavior is proven against the production
   engine before merge?

## Verdict

The working hypothesis holds against the code. The SDK surface needs zero changes, `.distinct()`
is genuinely unnecessary, and the serializer FK-narrowing hole is real and separate from queryset
scoping. Proceed to `sdd-propose` with the four open questions above resolved explicitly rather
than inherited as silent assumptions.
