# Tasks: Organization/Project/Environment Tenancy with RBAC

> **Size note.** This exceeds the tasks-skill's ~530-word guidance. The user's task requires a
> Review Workload Forecast, ordering rationale, an explicit security cut line, per-slice
> rollback notes, a fused test-infrastructure unit, and full spec traceability across a
> 7-slice change. Compressing further would drop required content — the same deliberate
> deviation `design.md` records for its own 800-word budget.

## Review Workload Forecast

This session's `review_budget_lines` = **800** (collected at SDD session start). The skill
template's guard-line label below literally says "400-line budget risk" for downstream
parser compatibility — read its value against the actual 800-line budget, not the label text.

| Field | Value |
|---|---|
| Estimated changed lines (total, 7 slices) | ~2,700–3,600 (proposal forecast ~2,805–3,720; F2 revises slice 2 down, F3 adds one file to slice 4) |
| Per-slice risk against the 800-line budget | Slice 1 Low · Slice 2 Medium (fused, cannot split) · Slice 3 Low–Medium · Slice 4 Medium · Slice 5 Low–Medium · Slice 6 Medium–High (splittable) · Slice 7 Medium |
| Chained PRs recommended | Yes |
| Suggested split | 7 slices, PR 1 → PR 2 → … → PR 7 (PR 6 may split into 6a/6b) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending — orchestrator collects from the user before apply |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

Why "High" despite no single slice forcing the 800-line ceiling: the total crosses it roughly
3.5x over 7 dependency-ordered PRs, two slices (2, 6) sit close to the ceiling, and slice 2
cannot be split if it overruns (schema + fixtures must land together — see D7 test-infra
rationale below). That combination, not any one slice, is what drives the rating.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Postgres service in CI | PR 1 (→ main) | N/A — CI config only, no unit under test | Push branch; confirm `Backend (lint + tests)` job passes with `postgres:18-alpine` service | `git revert` the `.github/workflows/ci.yml` diff; zero functional impact |
| 2 | Tenancy schema + test fixtures (fused) | PR 2 | `pytest tests/unit/test_models.py tests/conftest.py -k tenancy`, then full `pytest` | `python manage.py migrate` on local Postgres; `migrate tenancy zero` to prove the reverse works pre-second-project | Code revert clean; migration revert works **only before** a 2nd project holds a `production` env (sharp edge, see below) |
| 3 | Capability resolver (pure library) | PR 3 | `pytest tests/unit/test_capabilities.py tests/unit/test_scoping.py` | N/A — pure functions, not yet wired to a viewset; no live scenario exists to exercise | `git revert`; nothing else depends on this code yet, so nothing regresses |
| 4 | Enforcement wiring (9 viewsets, 5 serializers) | PR 4 | `pytest tests/integration/test_tenant_scoping.py`, then full `pytest` | Manual: env VIEWER GETs a foreign env's flag → 404; PATCH without `flag.edit` → 403; POST override with foreign `flag_id` → 400 | `git revert`; **re-opens the vulnerability** this slice closes — do not revert alone on a live deployment |
| 5 | Analytics scoping | PR 5 | `pytest tests/integration/test_analytics_api.py` | `GET /api/v1/analytics/overview/?environment=<foreign>` → 404; `?environment=not-a-uuid` → 400 | `git revert`; no schema change |
| 6 | Org & member management (feature work) | PR 6 | `pytest tests/integration/test_registration.py tests/integration/test_org_management_api.py` | Register 2 users → 2 orgs; grant project/env roles via API; exceed a plan's seat limit → 400 `seat_limit_reached` | `git revert`; no schema change (reuses slice 2's tables) |
| 7 | Frontend: switcher, members UI, grant preview | PR 7 | N/A backend; `npm run lint && npm run build` (frontend/) | Switch project in UI, confirm lists re-filter; build a grant in Members, confirm preview matches post-save capabilities | `git revert`; frontend-only |

## Slice Ordering Rationale

Strict dependency chain, 1→2→3→4→5→6→7:

- **Slice 1 is non-negotiable first.** The migration's `AlterUniqueTogether` reverse behaves
  differently on SQLite vs Postgres (sharp edge below). Every later migration must be exercised
  against the production engine from its first commit, not retrofitted once CI is already
  SQLite-green.
- **Slice 2 before 3.** `tenancy.Project` and `Environment.project` must exist before any
  capability helper can query them.
- **Slice 3 before 4.** `resolve_capabilities`, the `*_with` helpers, and `HasCapability` are
  pure/unwired and independently testable (12 RED tests, design D7 §1-6) — this is what keeps
  slice 4 a wiring review instead of a wiring-plus-semantics review.
- **Slice 4 before 5.** Analytics scoping reuses the exact `environments_with(u, ANALYTICS_VIEW)`
  helper wired in slice 4.
- **Slice 5 before 6.** New org/member-management endpoints inherit the same enforcement stack;
  wiring first means they are tenant-scoped from their first commit.
- **Slice 6 before 7.** The frontend's members screen and effective-capability preview consume
  slice 6's API.

## The Security Cut Line

**Slices 1–5 close the live vulnerability** (no tenant isolation — every authenticated user
reads/writes every other tenant's data today): Postgres-verified migration, tenant tables, the
capability resolver, all 9 viewsets + 5 serializers scoped, `IsDashboardUser` replacing the
global `IsAuthenticated`, analytics bounded. After slice 5: cross-tenant reads 404, cross-tenant
FK writes 400, missing-capability writes 403 — and grants can still be made through `/admin/`
(registered in slice 2), so the system is secure even before slice 6 ships.

**Slices 6–7 are feature work**: the self-service org/member-management API and its UI. Stopping
after slice 5 leaves a secure but administrator-only system (no self-service grants yet). The
user may stop at the slice-5 boundary if only the security fix is wanted now.

## Rollback Notes — the Sharp Edge

Reversing `core_flags.0003`'s `AlterUniqueTogether` re-imposes global uniqueness on
`Environment.key`. Once two projects each hold a `production` environment, the reverse **fails
with `IntegrityError`** — Postgres fails at `ADD CONSTRAINT` validation, SQLite fails inside
`_remake_table`'s row-by-row rebuild, with different error text and a different partial-
transaction shape. Slice-2 revert is supported **only before a second project exists**; past
that point the only supported path is forward-fix. This is the concrete reason slice 1 (Postgres
in CI) must land first — SQLite-only CI would never surface the divergence.

---

## Phase 1 — Slice 1: Postgres in CI

*Traces: enables Postgres-verified migration behavior required by Tenancy Hierarchy
(tenancy-model spec).*

- [x] 1.1 Add a `postgres:18-alpine` service + health check to the `backend` job in
      `.github/workflows/ci.yml`. Version matches production (`compose.yml:5`,
      `compose.dev.yml:5`) — the point of this slice is that CI and production share an engine.
- [x] 1.2 Add `DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT` env vars at job level
      (flips `config/settings.py:94`'s engine branch; `psycopg2-binary` already in
      `requirements/base.txt`).
- [x] 1.3 Push the branch; confirm the `Backend (lint + tests)` job name is unchanged
      (branch-protection contract) and the existing 170 tests pass on Postgres.

## Phase 2 — Slice 2: Tenancy Schema + Test Infrastructure (fused, one PR)

*Traces: Tenancy Hierarchy (tenancy-model). Test infra ships WITH the NOT NULL migration per
design D7 — splitting them leaves CI red between merges.*

- [x] 2.1 RED — `tests/unit/test_models.py::test_environment_requires_project`: assert
      `Environment.objects.create(...)` without `project=` raises `IntegrityError` (design D7
      test 8). Fails: column is nullable/absent.
- [x] 2.2 RED — `tests/unit/test_models.py::test_two_projects_can_each_hold_production`
      (design D7 test 7). Fails: `unique_together` is still `("key",)`.
- [x] 2.3 GREEN — create `tenancy/models.py`: `Organization`, `Project`,
      `OrganizationMembership`, `ProjectMembership`, `EnvironmentMembership`, `Plan`, 3 role
      enums, named `UniqueConstraint`s, `Index(["user"])` per table, `CheckConstraint` on role.
- [x] 2.4 GREEN — modify `core_flags/models.py`: add `Environment.project` FK (lazy
      `"tenancy.Project"` ref), move `unique_together` to `("project", "key")`.
- [x] 2.5 GREEN — create `tenancy/migrations/0001_initial.py` (5 `CreateModel`; depends on
      `core_flags.0002` + `AUTH_USER_MODEL`).
- [x] 2.6 GREEN — create `core_flags/migrations/0003_environment_project.py`:
      `AddField(null=True)` → `RunPython(backfill_default_project, noop)` →
      `AlterField(null=False)` → `AlterUniqueTogether`; depends on `tenancy.0001`.
- [x] 2.7 GREEN — create `tenancy/admin.py` registering all five new models.
- [x] 2.8 Create `tests/conftest.py`: function-scoped `organization`, `project`, `environment`,
      `flag`, `make_project`/`make_environment`/`make_flag`, `user`, `grant`, `api_client`,
      `assert_membership_never_joined`.
- [x] 2.9 Convert the `setup_method` blocks that build an `Environment` to
      `@pytest.fixture(autouse=True) def _setup(self, project)`. **Correction against design
      F2**: measured 15 such blocks across 7 files, not 18/8 — `test_auth_refresh.py`'s 3
      `setup_method` blocks build no `Environment` and need no `project`, so they were left
      untouched. See Deviations in apply-progress.
- [x] 2.10 Add `project=project` to the 44 `Environment.objects.create(...)` sites (11 files,
      23 in `tests/unit/test_models.py`); leave the 82 `FeatureFlag.objects.create(environment=
      env, ...)` sites untouched (F2 — verified, not 126 sites).
- [x] 2.11 Add a `project` parameter to the module-level fixtures that build environments.
      **Correction against design F2**: measured 3 such fixtures across 3 files, not 6 — the
      other fixtures in those files (`client`, `sdk_client`) build no `Environment`.
- [x] 2.12 Confirm `tests/integration/test_admin_api.py:27-127` still sets up cleanly after its
      `setup_method` conversion; its `pass`-stub bodies stay unchanged (converting them to real
      tests is out of scope — design's open question).
- [x] 2.13 Run full `pytest` on local Postgres (170+ tests green), then
      `python manage.py migrate tenancy zero` to prove the pre-second-project reverse path.

## Phase 3 — Slice 3: Capability Resolver (pure library, no viewset wiring)

*Traces: Capability Catalogue by Level, Role to Capability Grants, Union Role Resolution,
The Carve-Out Trap (tenancy-model).*

- [ ] 3.1 RED — `tests/unit/test_capabilities.py::test_resolve_capabilities_matrix`: 100 role
      tuples (4 org × 5 project × 5 env, incl. "no membership") × full 15-capability assertion
      (design D7 test 1). Fails: `capabilities.py` does not exist.
- [ ] 3.2 RED — `test_union_org_admin_not_narrowed`: org `ADMIN` + project `VIEWER` still holds
      `flag.edit` (design D7 test 2).
- [ ] 3.3 RED — `test_narrow_implication_project_view_only`: env membership alone yields exactly
      `project.view` at project level and nothing else (design D7 test 3).
- [ ] 3.4 GREEN — create `tenancy/capabilities.py`: 15 capability constants,
      `ORG_ROLE_CAPS`/`PROJECT_ROLE_CAPS`/`ENV_ROLE_CAPS`, inverted `*_ROLES_GRANTING` maps,
      `resolve_capabilities()`, `max_seats()`. Unknown capability string raises `ValueError`.
- [ ] 3.5 RED — `tests/unit/test_scoping.py::test_environments_with_matches_resolve_capabilities`:
      the consistency invariant across the 100-tuple matrix (design D7 test 4). Fails:
      `scoping.py` does not exist.
- [ ] 3.6 RED — `test_no_membership_join`: `assert_membership_never_joined` over the 3 helpers ×
      every capability (design D7 test 5).
- [ ] 3.7 RED — `test_no_fan_out`: triple membership (org+project+env) on one environment, same
      capability, `environments_with(...).count() == 1` (design D7 test 6).
- [ ] 3.8 GREEN — create `tenancy/scoping.py`: `orgs_with`, `projects_with`,
      `environments_with`, `capabilities_for`, all join-free (design D4).
- [ ] 3.9 GREEN — create `tenancy/permissions.py`: `IsDashboardUser`, `HasCapability`,
      `TenantScopedViewSetMixin` — unwired, unit-tested standalone, not yet attached to a
      viewset.

## Phase 4 — Slice 4: Enforcement Wiring (9 viewsets, 5 serializers)

*Traces: Queryset Scoping Returns 404 Not 403, Serializer FK Narrowing Returns 400,
Capability-Gated Actions Return 403, No Superuser Bypass, Non-User Principal Fails Closed
(access-control); Environment Management + Tenant-Scoped Flag CRUD (flag-management delta).*

- [ ] 4.1 RED — `tests/integration/test_tenant_scoping.py`: two tenants; cross-tenant GET →
      404, cross-tenant FK POST → 400, capability-less write → 403 (design D7 test 9).
- [ ] 4.2 RED — `test_x_api_key_on_dashboard_route_returns_403`: assert status 403 and that no
      `AttributeError` is raised (design D7 test 10).
- [ ] 4.3 RED — `test_router_coverage`: walk `router.registry` for `core_flags/api/urls.py` and
      `sdk_api/api/urls.py`; every viewset subclasses `TenantScopedViewSetMixin` (design D7
      test 11).
- [ ] 4.4 GREEN — `config/settings.py:187-189`: global `DEFAULT_PERMISSION_CLASSES` →
      `tenancy.permissions.IsDashboardUser`; `authentication/views.py:164,181` move to the
      same class.
- [ ] 4.5 GREEN — `core_flags/api/views.py`: apply
      `(TenantScopedViewSetMixin, QueryParamFilterMixin, ModelViewSet)` MRO order to
      `EnvironmentViewSet`, `FeatureFlagViewSet`, `StrategyRuleViewSet`, `ConditionViewSet`,
      `FlagOverrideViewSet`; set `environment_lookup`/`capability_for_action`; add
      `rotate_api_key` action.
- [ ] 4.6 GREEN — `sdk_api/api/views.py`: scope `SDKRegistrationViewSet`,
      `EvaluationLogViewSet` the same way.
- [ ] 4.7 GREEN — `tenancy/api/{views,serializers,urls}.py`: new `OrganizationViewSet`,
      `ProjectViewSet`.
- [ ] 4.8 GREEN — `core_flags/api/serializers.py`: narrow `FeatureFlagSerializer.environment`,
      `StrategyRuleSerializer.flag`, `ConditionSerializer.rule`, `FlagOverrideSerializer.flag`,
      **and** `EnvironmentSerializer.project` (F3 — the fifth field, the root-level hole).
- [ ] 4.9 RED — `test_environment_serializer_project_narrowed`: POST
      `/api/v1/environments/` with a foreign project UUID → 400, no row created (spec:
      "Root-level cross-tenant write").
- [ ] 4.10 RED — `test_move_environment_to_foreign_project_rejected`: PATCH an existing
      environment's `project` to a foreign UUID → 400, assignment unchanged (spec: "Moving an
      environment into another tenant's project rejected").
- [ ] 4.11 GREEN — confirm 4.9/4.10 pass via 4.8's narrowing.
- [ ] 4.12 RED then GREEN — `test_serializer_without_request_context`: write → 400, read →
      still serializes (design's `.none()` decision).
- [ ] 4.13 Confirm full `pytest` green; confirm the four protected SDK files
      (`sdk_api/views.py`, `sdk_api/authentication.py`, `sdk_api/payloads.py`,
      `core_flags/notifications.py`) are untouched (F6 / proposal success criterion).

## Phase 5 — Slice 5: Analytics Scoping

*Traces: Analytics Scoping Is Always Bounded (access-control).*

- [ ] 5.1 RED — `tests/integration/test_analytics_api.py::test_no_params_scopes_to_visible_
      environments` (design D7 test 12).
- [ ] 5.2 RED — scenarios: `?environment=<foreign>` → 404, `?environment=not-a-uuid` → 400 (and
      the `?project=` equivalents), no-grants → 200 zeros, `environments.total` reflects scope.
- [ ] 5.3 GREEN — `analytics/services.py`: delete `_scope_by_environment`'s none-escape; the
      four `build_*` functions take `environments: QuerySet[Environment]` first, no default;
      add `_scope(qs, environments, lookup)`.
- [ ] 5.4 GREEN — `analytics/api/views.py`: replace `_environment_id` with
      `_scoped_environments()` (F4: malformed UUID → 400, not treated as absent); add
      `@permission_classes([IsDashboardUser])` to all four `@api_view`s.
- [ ] 5.5 Confirm full `pytest` green.

## Phase 6 — Slice 6: Org & Member Management (feature work — security cut line above this)

*Traces: Self-Registration Auto-Provisions an Organization, Owner/Admin Creates and Attaches
Users, Per-Project and Per-Environment Role Grants, Seat Accounting Against the Plan
(organization-management); Organization Ownership Invariant (tenancy-model). Splittable into
6a/6b if it approaches the 800-line budget — no shared schema between the two halves.*

- [ ] 6.1 RED — `tests/integration/test_registration.py::test_registration_auto_provisions_
      organization`: new user → exactly one `Organization`, `OWNER` membership.
- [ ] 6.2 GREEN — `authentication/views.py`: registration creates `Organization` +
      `OrganizationMembership(role=OWNER)` in one transaction.
- [ ] 6.3 RED — `test_admin_creates_member` (consumes a seat) / `test_non_privileged_cannot_
      create_member` → 403.
- [ ] 6.4 RED — `test_seat_limit`: under limit creates; at boundary → 400
      `seat_limit_reached`; `COMMUNITY` never blocks; removing frees immediately; deactivated
      user still counts; downgrade doesn't evict existing members.
- [ ] 6.5 GREEN — `tenancy/api/{views,serializers,urls}.py`: member-creation endpoint with
      `select_for_update()` on the `Organization` row for the seat check.
      *(— 6a boundary: registration + org membership + seats.)*
- [ ] 6.6 RED — `test_grant_project_role` / `test_grant_environment_role` /
      `test_grant_rejected_without_org_membership`.
- [ ] 6.7 GREEN — grant endpoints for `ProjectMembership` and `EnvironmentMembership`,
      enforcing the org-membership prerequisite.
- [ ] 6.8 RED — `test_last_owner_cannot_be_removed`.
- [ ] 6.9 GREEN — enforce the ownership invariant on membership delete/demote.
- [ ] 6.10 GREEN — `POST /api/v1/tenancy/effective-capabilities/preview/`: takes proposed
      unsaved roles, answers through `resolve_capabilities` (design D10); requires
      `project.manage_members` on every referenced project.
      *(— 6b boundary: project/env grant CRUD + ownership invariant + preview.)*

## Phase 7 — Slice 7: Frontend (feature work)

*Traces: UI surface for organization-management requirements; the effective-capability
preview is the design's mitigation for its top risk (admins misreading union/carve-out).*

- [ ] 7.1 Read `frontend/node_modules/next/dist/docs/` before writing any component (per
      `frontend/AGENTS.md` — this Next.js version differs from training data).
- [ ] 7.2 Create `frontend/src/lib/tenant-context.tsx`: org/project state + `localStorage`,
      modelled on `auth-context.tsx`.
- [ ] 7.3 Modify `frontend/src/app/dashboard/layout.tsx`: nest `TenantProvider` inside
      `AuthProvider`.
- [ ] 7.4 Modify `frontend/src/lib/api.ts`: add `project?: string` param on
      `environmentsApi.list`, `flagsApi.list`, and all four `analyticsApi` functions via the
      existing `buildQuery`; add tenancy + members API calls.
- [ ] 7.5 Modify `frontend/src/components/layout/dashboard-nav.tsx`: org/project switcher,
      Members nav entry.
- [ ] 7.6 Create `frontend/src/app/dashboard/members/page.tsx`: additive grants list (never a
      checkbox grid — union cannot carve out) + effective-capability preview against 6.10's
      endpoint.
- [ ] 7.7 Modify the 6 pages under `frontend/src/app/dashboard/{page,environments,flags,
      flags/[id]/rules,monitoring}` to read `currentProject` and forward `?project=` on the
      wire only (not in the app's own URLs).
- [ ] 7.8 Run `npm run lint && npm run build` in `frontend/`; manually confirm switching
      project re-filters lists, and a proposed grant's preview matches the capability set
      observed after saving.
