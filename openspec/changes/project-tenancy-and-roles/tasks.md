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

- [x] 3.1 RED — `tests/unit/test_capabilities.py::test_resolve_capabilities_matrix`: 100 role
      tuples (4 org × 5 project × 5 env, incl. "no membership") × full 15-capability assertion
      (design D7 test 1). Fails: `capabilities.py` does not exist. **Correction against
      design/D7/D3**: the spec's Capability Catalogue by Level table (`specs/tenancy-model/
      spec.md`) enumerates **16** distinct capability strings (5 org + 6 project + 5
      environment), not 15 — `org.view, org.manage_members, org.manage, org.delete,
      project.create, project.view, project.manage, project.manage_members, project.delete,
      environment.create, environment.delete, environment.view, environment.manage, flag.edit,
      override.manage, analytics.view`. Implemented all 16, since the spec is the behavioral
      authority per this session's instructions; the 100-tuple matrix count (4×5×5) is
      unaffected since that comes from role counts, not capability counts. See Deviations.
- [x] 3.2 RED — `test_union_org_admin_not_narrowed`: org `ADMIN` + project `VIEWER` still holds
      `flag.edit` (design D7 test 2).
- [x] 3.3 RED — `test_narrow_implication_project_view_only`: env membership alone yields exactly
      `project.view` at project level and nothing else (design D7 test 3).
- [x] 3.4 GREEN — create `tenancy/capabilities.py`: 16 capability constants (see 3.1 correction),
      `ORG_ROLE_CAPS`/`PROJECT_ROLE_CAPS`/`ENV_ROLE_CAPS`, inverted `*_ROLES_GRANTING` maps,
      `resolve_capabilities()`, `max_seats()`. Unknown capability string raises `ValueError`
      (`validate_capability`). **Note**: neither design.md nor the specs give the exact
      role→capability grant tables (only example scenarios); this task authored a concrete,
      internally-consistent policy from those scenarios plus the `ADMIN ⊇ EDITOR ⊇ OPERATOR ⊇
      VIEWER` cumulative-role convention implied throughout. See Deviations for the exact tables.
- [x] 3.5 RED — `tests/unit/test_scoping.py::test_environments_with_matches_resolve_capabilities`:
      the consistency invariant across the 100-tuple matrix (design D7 test 4). Fails:
      `scoping.py` does not exist.
- [x] 3.6 RED — `test_no_membership_join`: `assert_membership_never_joined` over the 3 helpers ×
      every capability (design D7 test 5).
- [x] 3.7 RED — `test_no_fan_out`: triple membership (org+project+env) on one environment, same
      capability, `environments_with(...).count() == 1` (design D7 test 6).
- [x] 3.8 GREEN — create `tenancy/scoping.py`: `orgs_with`, `projects_with`,
      `environments_with`, `capabilities_for`, all join-free (design D4). Added
      `test_project_view_narrow_special_case` to `test_scoping.py` to cover D4's documented
      asymmetry directly, and `test_unknown_capability_raises_on_all_three_helpers` per the
      Testing Strategy table's `ValueError` requirement (not separately numbered in tasks.md,
      but required by this session's constraints and design's Testing Strategy section).
- [x] 3.9 GREEN — create `tenancy/permissions.py`: `IsDashboardUser`, `HasCapability`,
      `TenantScopedViewSetMixin` — unwired, unit-tested standalone, not yet attached to a
      viewset. Added `tests/unit/test_permissions.py` (13 tests) — not explicitly listed as a
      RED task in this phase, but Strict TDD Mode requires a failing test before any production
      code, and the task description itself says "unit-tested standalone".

### Slice 3 deviations from the planning artifacts

1. **16 capabilities, not 15.** `design.md` and task 3.4 both say 15. The Capability Catalogue
   in `specs/tenancy-model/spec.md` lists 16 distinct strings (5 org + 6 project + 5
   environment). The spec is the behavioral authority, so 16 were implemented.

2. **The role -> capability grant table was never specified.** Neither `design.md` nor the specs
   define it; they give scenario examples only. It was authored during implementation and then
   reviewed with the user, which surfaced (3).

3. **`OrganizationRole.OWNER` was removed** (user decision, 2026-08-28). The authored table gave
   OWNER and ADMIN identical capability sets, so OWNER distinguished nothing while still
   occupying the enum, the database CheckConstraint and any future assignment UI. The
   organization level now has ADMIN and USER (VIEWER was renamed in the same slice, user
   decision), matching Flagsmith's two-role organisation
   model, which was already this change's reference.

   Consequence, deliberately accepted: an organization ADMIN is a full key to the account. It
   holds `org.delete`, and `on_delete=CASCADE` carries every project, environment, flag, rule
   and override with it. **The members UI (slice 7) must warn when assigning it.**

   Guarded by `test_no_two_roles_at_one_level_are_interchangeable`, which asserts at all three
   levels that no two roles grant identical capabilities, so the class of defect cannot return
   silently. Migration `tenancy/0002_drop_organization_owner_role` replaces the CheckConstraint.

## Phase 4 — Slice 4: Enforcement Wiring (9 viewsets, 5 serializers)

*Traces: Queryset Scoping Returns 404 Not 403, Serializer FK Narrowing Returns 400,
Capability-Gated Actions Return 403, No Superuser Bypass, Non-User Principal Fails Closed
(access-control); Environment Management + Tenant-Scoped Flag CRUD (flag-management delta).*

- [x] 4.1 RED — `tests/integration/test_tenant_scoping.py`: two tenants; cross-tenant GET →
      404, cross-tenant FK POST → 400, capability-less write → 403 (design D7 test 9). Observed
      RED (404/400/403 assertions failed against unwired viewsets) before GREEN.
- [x] 4.2 RED — `test_x_api_key_on_dashboard_route_returns_403`: assert status 403 and that no
      `AttributeError` is raised (design D7 test 10). Observed RED (200, not 403) before GREEN.
- [x] 4.3 RED — `test_router_coverage`: walk `router.registry` for `core_flags/api/urls.py` and
      `sdk_api/api/urls.py`; every viewset subclasses `TenantScopedViewSetMixin` (design D7
      test 11). Observed RED (`AssertionError` on the first unscoped viewset) before GREEN.
- [x] 4.4 GREEN — `config/settings.py:187-189`: global `DEFAULT_PERMISSION_CLASSES` →
      `tenancy.permissions.IsDashboardUser`; `authentication/views.py:164,181` move to the
      same class.
- [x] 4.5 GREEN — `core_flags/api/views.py`: apply
      `(TenantScopedViewSetMixin, QueryParamFilterMixin, ModelViewSet)` MRO order to
      `EnvironmentViewSet`, `FeatureFlagViewSet`, `StrategyRuleViewSet`, `ConditionViewSet`,
      `FlagOverrideViewSet`; set `environment_lookup`/`capability_for_action`; add
      `rotate_api_key` action. See Deviations #1 and #2 below for two bugs this wiring
      surfaced in the already-implemented `tenancy/permissions.py`.
- [x] 4.6 GREEN — `sdk_api/api/views.py`: scope `SDKRegistrationViewSet`,
      `EvaluationLogViewSet` the same way.
- [x] 4.7 GREEN — `tenancy/api/{views,serializers,urls}.py`: new `OrganizationViewSet`,
      `ProjectViewSet`. Implemented as `ReadOnlyModelViewSet` — see Deviation #3.
- [x] 4.8 GREEN — `core_flags/api/serializers.py`: narrow `FeatureFlagSerializer.environment`,
      `StrategyRuleSerializer.flag`, `ConditionSerializer.rule`, `FlagOverrideSerializer.flag`,
      **and** `EnvironmentSerializer.project` (F3 — the fifth field, the root-level hole). Added
      `tenancy/serializers.py::CapabilityScopedFKMixin` (design D5/file list; not separately
      numbered as a task but required to implement 4.8).
- [x] 4.9 RED — `test_environment_serializer_project_narrowed`: POST
      `/api/v1/environments/` with a foreign project UUID → 400, no row created (spec:
      "Root-level cross-tenant write"). Observed RED (`IntegrityError`, since `project` did not
      yet exist as a serializer field) before GREEN.
- [x] 4.10 RED — `test_move_environment_to_foreign_project_rejected`: PATCH an existing
      environment's `project` to a foreign UUID → 400, assignment unchanged (spec: "Moving an
      environment into another tenant's project rejected"). Observed RED (200, not 400) before
      GREEN.
- [x] 4.11 GREEN — confirm 4.9/4.10 pass via 4.8's narrowing. Also added
      `test_own_project_accepted_on_create` as the required triangulation case (a project the
      user does hold `environment.create` on must still succeed) — see Deviation #1.
- [x] 4.12 RED then GREEN — `test_serializer_without_request_context`: write → 400, read →
      still serializes (design's `.none()` decision). Observed RED (write validated as `True`
      with no narrowing at all) before GREEN.
- [x] 4.13 Confirm full `pytest` green; confirm the four protected SDK files
      (`sdk_api/views.py`, `sdk_api/authentication.py`, `sdk_api/payloads.py`,
      `core_flags/notifications.py`) are untouched (F6 / proposal success criterion). 374/374
      green on Postgres 18; `git diff --stat` on the four files is empty.

### Slice 4 deviations from the planning artifacts

1. **`EnvironmentViewSet.create` cannot use `HasCapability`'s generic pre-check.**
   `HasCapability.has_permission`'s unsafe-method pre-check asks
   `environments_with(u, capability).exists()` — "does any *existing* Environment row grant
   this". For every other viewset the gated capability lives at the level being queried
   (`FLAG_EDIT` needs an existing Environment; the Flag itself need not exist yet). But
   `ENVIRONMENT_CREATE` is a *project*-level capability, and the pre-check queries `Environment`
   rows — the exact model being created. On a project's *first* environment, that queryset is
   empty even when the user genuinely holds `ENVIRONMENT_CREATE` via `ProjectMembership`,
   producing a false 403 ahead of Layer 2 ever running. Neither `design.md` nor `tasks.md`
   anticipated this. Fix: `EnvironmentViewSet.get_permissions()` excludes `HasCapability` only
   for the `create` action, relying solely on Layer 2 (`EnvironmentSerializer.project`
   narrowing) — consistent with design D5's own statement that "Layer 2 is the ONLY create-time
   gate" for exactly this reason. Every other action (`update`, `partial_update`, `destroy`,
   `rotate_api_key`) operates on an environment that already exists, where the pre-check is
   meaningful, so only `create` is excluded. `tenancy/permissions.py` itself is unchanged for
   this point. Proven by `test_own_project_accepted_on_create` (201 with a legitimate,
   first-ever grant) alongside `test_foreign_project_rejected_on_create` (400).

2. **Two bugs found in the already-implemented, already-unit-tested `tenancy/permissions.py`
   (slice 3) while wiring it to real HTTP requests, both fixed in this slice:**
   - `HasCapability.has_object_permission` never bypassed `SAFE_METHODS`, unlike
     `has_permission`. A plain `GET` on a visible object called
     `capability_for_action(view.action)` with `view.action == "retrieve"`, which is never
     mapped in any viewset's `capability_map` (only unsafe actions are), raising
     `ImproperlyConfigured` (500) on every single-object read. Fixed by adding the same
     `SAFE_METHODS` bypass already present in `has_permission`. No RED task in `tasks.md`
     covers object-level reads specifically, but `test_cross_tenant_read_returns_404` and the
     full existing GET-based integration suite would not pass without this fix.
   - Neither `has_permission` nor `has_object_permission` handled `view.action is None`. DRF
     resolves `view.action` from the router's method map in `initialize_request`, *before*
     dispatch decides the HTTP method is unsupported. A verb a viewset does not implement (e.g.
     `PATCH`/`DELETE` on the append-only `FlagOverrideViewSet`) has no `action_map` entry, so
     `view.action` is `None`; `capability_for_action(None)` then raised `ImproperlyConfigured`
     (500) instead of letting DRF's own dispatch reach `http_method_not_allowed` (405). Fixed by
     returning `True` (permit) when `view.action is None` in both methods, deferring entirely to
     DRF's own method-not-allowed handling. Surfaced by the pre-existing
     `test_is_append_only` test in `tests/integration/test_monitoring_api.py`, which predates
     this slice and was not itself modified.
   Both fixes are additive branches; none of slice 3's 13 `tests/unit/test_permissions.py`
   tests needed changes and all still pass unmodified.

3. **`tenancy.api.OrganizationViewSet`/`ProjectViewSet` implemented as `ReadOnlyModelViewSet`,
   not full `ModelViewSet`.** Task 4.7 says "new `OrganizationViewSet`, `ProjectViewSet`" without
   specifying CRUD scope. Design's five-field FK-narrowing table (F3/D5) does not include
   `Project.organization` — if these viewsets accepted writes with a plain
   `PrimaryKeyRelatedField` for `organization`, any authenticated user could `POST` a `Project`
   under another organization's UUID, an unnarrowed root-level hole one level *above* the one
   this slice closes. No task or spec scenario in Phase 4 requires organization/project creation
   via this API (`Owner/Admin creates and attaches users` is explicitly slice 6's traceability).
   Given the choice between inventing an unreviewed, unnarrowed write path and keeping these two
   viewsets read-scoped (satisfying the "Queryset Scoping Returns 404" requirement, which does
   name `OrganizationViewSet`/`ProjectViewSet`, and task 4.3's router semantics), read-only was
   chosen. Writes belong to slice 6's grant/member-management endpoints, which will need to
   narrow `Project.organization` when they add them.

4. **`OrganizationViewSet`/`ProjectViewSet` are intentionally excluded from the task 4.3
   router-coverage test.** `TenantScopedViewSetMixin.get_queryset()` is hard-coded to
   `environments_with(u, ENVIRONMENT_VIEW)` (design D5's own snippet) — it cannot express
   `orgs_with`/`projects_with` scoping for models that sit *above* `Environment` in the
   hierarchy. Design D4 itself scopes the router-walk test to `core_flags/api/urls.py` and
   `sdk_api/api/urls.py` only (not `tenancy/api/urls.py`), which resolves this without needing
   an allowlist: the test asserts exactly the 5 + 2 = 7 viewsets in those two routers.

## Phase 5 — Slice 5: Analytics Scoping

*Traces: Analytics Scoping Is Always Bounded (access-control).*

- [x] 5.1 RED — `tests/integration/test_analytics_api.py::test_no_params_scopes_to_visible_
      environments` (design D7 test 12).
- [x] 5.2 RED — scenarios: `?environment=<foreign>` → 404, `?environment=not-a-uuid` → 400 (and
      the `?project=` equivalents), no-grants → 200 zeros, `environments.total` reflects scope.
- [x] 5.3 GREEN — `analytics/services.py`: delete `_scope_by_environment`'s none-escape; the
      four `build_*` functions take `environments: QuerySet[Environment]` first, no default;
      add `_scope(qs, environments, lookup)`.
- [x] 5.4 GREEN — `analytics/api/views.py`: replace `_environment_id` with
      `_scoped_environments()` (F4: malformed UUID → 400, not treated as absent); add
      `@permission_classes([IsDashboardUser])` to all four `@api_view`s.
- [x] 5.5 Confirm full `pytest` green.

## Phase 6 — Slice 6: Org & Member Management (feature work — security cut line above this)

*Traces: Self-Registration Auto-Provisions an Organization, Owner/Admin Creates and Attaches
Users, Per-Project and Per-Environment Role Grants, Seat Accounting Against the Plan
(organization-management); Organization Administration Invariant (tenancy-model). Splittable into
6a/6b if it approaches the 800-line budget — no shared schema between the two halves.*

- [x] 6.1 RED — `tests/integration/test_registration.py::test_registration_auto_provisions_
      organization`: new user -> exactly one `Organization`, `ADMIN` membership.
- [x] 6.2 GREEN — `authentication/views.py`: registration creates `Organization` +
      `OrganizationMembership(role=ADMIN)` in one transaction.
- [x] 6.3 RED — `test_admin_creates_member` (consumes a seat) / `test_non_privileged_cannot_
      create_member` → 403.
- [x] 6.4 RED — `test_seat_limit`: under limit creates; at boundary → 400
      `seat_limit_reached`; `COMMUNITY` never blocks; removing frees immediately; deactivated
      user still counts; downgrade doesn't evict existing members.
- [x] 6.5 GREEN — `tenancy/api/{views,serializers,urls}.py`: member-creation endpoint with
      `select_for_update()` on the `Organization` row for the seat check.
      *(— 6a boundary: registration + org membership + seats.)* **6a COMPLETE — 393/393 tests
      green on Postgres, ruff clean. Measured total changed lines on this branch: 518 (258
      tracked diff + 260 in three untracked new files, including the ~160-line orchestrator
      rename carryover). 6b deferred to its own PR per the 800-line budget guard: 6b's own
      scope (grant CRUD for two membership types, admin-invariant enforcement including new
      update/delete membership endpoints, and the effective-capabilities preview mirroring
      `resolve_capabilities`) was estimated at 700-900 lines on its own, which would have run
      well past 800 combined with 6a. Stopped cleanly at this boundary rather than overrunning
      or compressing by dropping tests.**
- [x] 6.6 RED — `test_grant_project_role` / `test_grant_environment_role` /
      `test_grant_rejected_without_org_membership`.
- [x] 6.7 GREEN — grant endpoints for `ProjectMembership` and `EnvironmentMembership`,
      enforcing the org-membership prerequisite.
- [x] 6.8 RED - `test_last_admin_cannot_be_removed` and
      `test_last_admin_cannot_be_demoted`. `OrganizationRole.OWNER` no longer exists (slice 3);
      the invariant now protects the last `ADMIN`, and the lockout it prevents is unchanged.
- [x] 6.9 GREEN - enforce the administration invariant on organization membership delete
      and demote.
- [x] 6.10 GREEN — `POST /api/v1/tenancy/effective-capabilities/preview/`: takes proposed
      unsaved roles, answers through `resolve_capabilities` (design D10); requires
      `project.manage_members` on every referenced project.
      *(— 6b boundary: project/env grant CRUD + ownership invariant + preview.)*
      **6b COMPLETE — 406/406 tests green on Postgres (393 baseline + 13 new), ruff clean.
      Measured changed lines: 582 (297 tracked diff across `tenancy/api/{views,serializers,
      urls}.py` + 285 in three new untracked test files). New endpoints:
      `POST /api/v1/tenancy/project-memberships/`, `POST /api/v1/tenancy/
      environment-memberships/` (both narrow their `project`/`environment` FK via
      `CapabilityScopedFKMixin` to `project.manage_members`, per the spec's single-capability
      gate for both grant kinds), `PATCH`/`DELETE /api/v1/tenancy/organization-memberships/{id}/`
      (administration invariant under `select_for_update()` on the org's `ADMIN` rows), and
      `POST /api/v1/tenancy/effective-capabilities/preview/` (narrows `organization` too, so an
      invisible org 400s the same way any other narrowed FK does).**

## Phase 7 - Slice 7: Frontend (feature work)

*Split into 7a and 7b after the rebase onto slice 8. 7a is the tenant switcher and
`?project=` threading; 7b is the members screen, which is a self-contained 718-line page and
had to be rewired to the membership listing slice 8 added. Shipping them together would have
been one 1147-line PR, half of it a screen already known to need rework.*

*Traces: UI surface for organization-management requirements; the effective-capability
preview is the design's mitigation for its top risk (admins misreading union/carve-out).*

- [x] 7.1 Read `frontend/node_modules/next/dist/docs/` before writing any component (per
      `frontend/AGENTS.md` — this Next.js version differs from training data). Read
      `01-getting-started/03-layouts-and-pages.md` and `05-server-and-client-components.md`;
      no server-component/route-convention change affects this slice (every touched file is
      already `'use client'`).
- [x] 7.2 Create `frontend/src/lib/tenant-context.tsx`: org/project state + `localStorage`,
      modelled on `auth-context.tsx`.
- [x] 7.3 Modify `frontend/src/app/dashboard/layout.tsx`: nest `TenantProvider` inside
      `AuthProvider`.
- [x] 7.4 Modify `frontend/src/lib/api.ts`: add `project?: string` param on
      `environmentsApi.list`, `flagsApi.list`, and all four `analyticsApi` functions via the
      existing `buildQuery`; add tenancy + members API calls. Deviation: also added `project`
      to the `Environment` interface (the serializer already returns it) and a `project`
      field to `environmentsApi.create` (the model has required it since slice 4; the create
      dialog had no way to supply it before this).
- [x] 7.5 Modify `frontend/src/components/layout/dashboard-nav.tsx`: org/project switcher,
      Members nav entry.
- [ ] 7.6 (7b) Create `frontend/src/app/dashboard/members/page.tsx`: additive grants list (never a
      checkbox grid — union cannot carve out) + effective-capability preview against 6.10's
      endpoint. Deviation (backend gap, not fixed here): `OrganizationMembershipViewSet`,
      `ProjectMembershipViewSet` and `EnvironmentMembershipViewSet` originally exposed no list
      endpoint, so this screen could only show members created in the current session. Slice 8
      added scoped listing to all three, and the session-local workaround and its in-UI
      limitation notice were removed.
- [x] 7.7 Modify the 6 pages under `frontend/src/app/dashboard/{page,environments,flags,
      flags/[id]/rules,monitoring}` to read `currentProject` and forward `?project=` on the
      wire only (not in the app's own URLs). `flags/[id]/rules/page.tsx` needed no change - it
      operates on one already tenant-scoped flag and calls no project-scoped list endpoint.
      The client-side filtering fallback this task originally needed was removed once slice 8
      wired the real `?project=` filter into `EnvironmentViewSet`/`FeatureFlagViewSet`.
- [x] 7.8 Ran `npm run lint && npm run build` in `frontend/` — both green. Manual confirmation
      in a running app NOT performed (no browser available to this agent) — unverified:
      switching project actually re-filtering the 6 pages' lists in a live session, and a
      proposed grant's preview matching the capability set observed after saving.

      wire only (not in the app's own URLs).
- [ ] 7.8 Run `npm run lint && npm run build` in `frontend/`; manually confirm switching
      project re-filters lists, and a proposed grant's preview matches the capability set
      observed after saving.

## Phase 8 - Slice 8: API gaps found while building the frontend

*Corrections to slices 4 and 6, discovered when slice 7 tried to consume the API. Not new
scope: each item is something an earlier slice's spec or design called for and its
implementation did not deliver.*

- [x] 8.1 RED - `POST /api/v1/environments/` from the dashboard's own payload shape.
      `EnvironmentSerializer` gained a required `project` since slice 4, but
      `environmentsApi.create` still sends only `{name, key}`, so **every environment
      creation from the UI has returned 400 since PR #12**. No frontend test exists to
      catch it. Pin the contract with a backend test.
      **Correction against this task's own "RED" label**: the added test
      (`test_create_payload_without_project_is_rejected`,
      `tests/integration/test_tenant_scoping.py`) passed immediately on the first run --
      slice 4's F3 fix already makes `project` a required, non-nullable
      `PrimaryKeyRelatedField` with no default, so DRF's own "this field is required"
      validation already rejects a payload missing it entirely, with no production code
      change needed here. This is a real gap (no test previously pinned this exact payload
      shape; `test_foreign_project_rejected_on_create` only covers a *present-but-foreign*
      project, not an *absent* one) but it is a regression-pinning test, not a RED→GREEN
      bug fix -- the backend was already correct; only the frontend caller (8.6) was not.
- [x] 8.2 RED - listing memberships: `GET` on organization, project and environment
      membership collections, each scoped and each proving a foreign tenant's rows are
      absent. Observed RED for the right reason before GREEN: `GET
      /organization-memberships/` returned 404 (no collection route registered at all,
      matching the design finding -- neither `list` nor `create` existed on that viewset);
      `GET /project-memberships/` and `/environment-memberships/` returned 405 (the
      collection route already existed for `create`, but `GET` was not mapped to it).
- [x] 8.3 GREEN - add `ListModelMixin` to `OrganizationMembershipViewSet`,
      `ProjectMembershipViewSet` and `EnvironmentMembershipViewSet`
      (`tenancy/api/views.py:110,183,198`). Without it DRF registers no collection route at
      all, so the members screen can create members and never enumerate them.
      **Capability chosen for reading**: each viewset's `get_queryset` now scopes by the
      *view* capability at its own level (`ORG_VIEW` / `PROJECT_VIEW` / `ENVIRONMENT_VIEW`),
      not the `*_MANAGE_MEMBERS` capability the create/update/destroy actions already
      require -- seeing who else shares your organization, project, or environment is
      ordinary visibility, not administration. `OrganizationMembershipViewSet` already drew
      this exact split (its `get_queryset` was `ORG_VIEW`-scoped while its mutations gate on
      `ORG_MANAGE_MEMBERS` via `_require_manage_permission`); this task extends the same
      split to the other two levels rather than inventing a new one.
- [x] 8.4 RED - `?project=` on `GET /api/v1/environments/` and `/api/v1/flags/`. Observed RED
      (both endpoints returned every visible row regardless of the `?project=` param;
      `?project=not-a-uuid` returned 200, not 400) before GREEN.
- [x] 8.5 GREEN - `EnvironmentViewSet` gains `QueryParamFilterMixin` and a `project` filter;
      `FeatureFlagViewSet.filter_fields` gains `environment__project` under the public name
      `project`. Design D10 called for this and slice 4 did not wire it, which is why slice 7
      needed a client-side filter fallback.
- [x] 8.6 GREEN - fix `environmentsApi.create` and the environments page dialog to send
      `project`. This branch has no `TenantContext`/tenancy API surface at all (slice 7's
      frontend work lives on a separate branch that will rebase on top of this one), so the
      minimal fix adds just enough surface for the dialog to work: a read-only
      `projectsApi.list()` (`GET /api/v1/tenancy/projects/`, already existed since task 4.7)
      and a project `<select>` in the create dialog, defaulting to the first project
      returned and disabling Create until one is selected. No other page, context, or
      component was touched.
- [x] 8.7 Confirm full `pytest` green on Postgres and `ruff check .` clean. 416/416 passed
      on Postgres 18 (406 baseline + 10 new), 6.01s; `ruff check .` clean.

