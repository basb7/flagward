```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:364ee8ecb0d1
verdict: pass_with_warnings
blockers: 0
critical_findings: 1
requirements: 17/18
scenarios: 49/50
test_command: DB_NAME=flagward DB_USER=postgres DB_PASSWORD=postgres DB_HOST=localhost DB_PORT=5433 .venv/bin/pytest -q
test_exit_code: 0
test_output_hash: sha256:2bffc5085bb197832e5ccc915d4afb875898168804d4aa0cf642e0a6c58e404d
build_command: cd frontend && npm run build
build_exit_code: 0
build_output_hash: sha256:1d3dd29db4bd29029acbdb61d9c6551ea349c4d6ed72084e0f4196cb0af643e5
```

## Verification Report

**Change**: project-tenancy-and-roles
**Repo state**: branch `main`, clean, `364ee8e` (PRs #9-#18 merged)
**Mode**: Strict TDD (backend) / Standard (frontend, per project convention)

### Completeness
| Metric | Value |
|---|---|
| Tasks total | 68 |
| Tasks complete | 68 (`[x]`) |
| Tasks incomplete | 0 |
| Task 7.8 manual browser confirmation | Explicitly NOT done (tasks.md says so; user confirmed this is a known gap) |

### Build & Tests Execution
**Backend tests** (Postgres 18-alpine, disposable container, port 5433): 418 passed, 0 failed.
Command: `DB_NAME=flagward DB_USER=postgres DB_PASSWORD=postgres DB_HOST=localhost DB_PORT=5433 .venv/bin/pytest -q`
Exit 0. Output hash sha256:2bffc508...20404d.

**Backend lint**: `.venv/bin/ruff check .` -> "All checks passed!"

**Frontend lint**: `npm run lint` (biome) -> "Checked 35 files in 33ms. No fixes applied."

**Frontend build**: `npm run build` (Next.js 16.3.3, Turbopack) -> compiled successfully, TypeScript clean, all 9 static/1 dynamic routes generated including `/dashboard/members`. Exit 0. Output hash sha256:1d3dd29d...43e5.

**No frontend test suite exists** -- zero `*.test.ts(x)`/`*.spec.ts(x)` files found anywhere under `frontend/src`; `package.json` has no `test` script; CI's frontend job is literally named "Frontend (lint + build)" with no test step (`.github/workflows` confirmed). Every frontend behavioral claim in this report is machine-verified (types/build/static route generation) only -- no browser was ever driven, matching the user's own stated constraint.

### Load-Bearing Claims -- Verdict

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Tenant isolation across 9 viewsets (404/400/403 split) | COMPLIANT, unevenly tested | `tenancy/permissions.py:70-117` (`TenantScopedViewSetMixin`/`HasCapability`), wired identically on `EnvironmentViewSet`, `FeatureFlagViewSet`, `StrategyRuleViewSet`, `ConditionViewSet`, `FlagOverrideViewSet` (`core_flags/api/views.py:30-196`), `SDKRegistrationViewSet`/`EvaluationLogViewSet` (`sdk_api/api/views.py:16-44`). `OrganizationViewSet`/`ProjectViewSet` (`tenancy/api/views.py:50-57,192-199`) scope manually via `orgs_with`/`projects_with` instead of the mixin. Direct HTTP 404-on-foreign-GET is runtime-tested for exactly one viewset (`FeatureFlagViewSet`, `tests/integration/test_tenant_scoping.py:39-45`) plus `OrganizationViewSet` indirectly via its nested `members` action (`tests/integration/test_organization_members.py:74-85`, 404). `ProjectViewSet` has zero direct test of this scenario -- its correctness rests entirely on the exhaustively-tested `projects_with` helper (`tests/unit/test_scoping.py`) and a one-line `get_queryset`, never exercised end-to-end. `test_every_registered_viewset_is_tenant_scoped` (`tests/integration/test_tenant_scoping.py:110-128`) structurally proves the mixin wiring for the 7 `core_flags`+`sdk_api` viewsets but explicitly excludes the 2 `tenancy`-router viewsets (comment: "expected the 5 core_flags + 2 sdk_api viewsets"). 400-on-cross-tenant-FK-write is directly tested (`test_cross_tenant_fk_write_returns_400`, plus the `TestEnvironmentSerializerProjectNarrowed`/tenant-scoped-flag-CRUD test family). 403-on-capability-shortfall directly tested (`test_capability_less_write_returns_403`). |
| 2 | No `is_superuser` bypass anywhere in DRF permission layer | Code-verified, UNTESTED at runtime | `rg is_superuser` across the whole non-test codebase returns zero hits outside `openspec/` documentation -- `HasCapability`/`IsDashboardUser` (`tenancy/permissions.py:22-67`) never reference it. However, zero test anywhere creates a superuser or asserts this scenario (`rg -i superuser|is_staff` and `create_superuser` across `tests/` -- zero matches). The spec's own scenario "Superuser with no membership is scoped like any user" has no covering test that ran. Flagged CRITICAL per this skill's rule that static evidence alone never proves a scenario. |
| 3 | Union role resolution -- no carve-out exists | COMPLIANT, thoroughly tested | `resolve_capabilities` (`tenancy/capabilities.py:124-145`) is a pure union with no subtraction path anywhere in its 21 lines. Exhaustively proven by `test_resolve_capabilities_matrix` and `test_environments_with_matches_resolve_capabilities` (parametrized over all 3x5x5 org/project/env role combinations x every capability, `tests/unit/test_capabilities.py`, `tests/unit/test_scoping.py:23-55`), plus dedicated `test_union_org_admin_not_narrowed`, `test_wide_grant_plus_attempted_carve_out_does_not_work`, `test_grants_at_different_levels_combine`. |
| 4 | Join-free scoping invariant -- no `.distinct()` needed | COMPLIANT | `tenancy/scoping.py` -- every `orgs_with`/`projects_with`/`environments_with` branch is a scalar `pk__in=`/`__in=.values()` subquery, no join. `assert_membership_never_joined` (`tests/conftest.py:119-132`) asserts `MEMBERSHIP_TABLES.isdisjoint(queryset.query.alias_map)` and `distinct is False`, run against all three helpers x every capability in the catalogue (`test_no_membership_join`, parametrized, `tests/unit/test_scoping.py:58-67`) plus a behavioral triple-membership fan-out guard (`test_no_fan_out`). `rg '\.distinct\('` over app code confirmed empty. |
| 5 | Preview cannot disagree with enforcement | COMPLIANT | `EffectiveCapabilitiesPreviewView.post` (`tenancy/api/views.py:265-`) calls `resolve_capabilities` directly (via the serializer) -- same function `capabilities_for` (`tenancy/scoping.py:83-106`) calls for real enforcement. Proven identical by direct behavioral test `test_preview_never_disagrees_with_enforcement` (`tests/integration/test_capability_preview.py:45-75`), which grants real roles, calls the preview, then compares its output against `capabilities_for` on the same user/environment. |
| 6 | SDK surface byte-identical; `Environment.api_key` still globally unique | COMPLIANT | `git diff f3dca5b..HEAD -- sdk_api/views.py sdk_api/authentication.py sdk_api/payloads.py core_flags/notifications.py` -> 0 lines changed (verified against the pre-change commit, not just current-file inspection). `core_flags/models.py:38`: `api_key = models.CharField(max_length=255, unique=True, db_index=True)` -- global uniqueness, untouched by the `Environment.key` scoping change. |
| 7 | Organization Administration Invariant -- never zero ADMIN, row-locked | COMPLIANT | `OrganizationMembershipViewSet.perform_update`/`perform_destroy` (`tenancy/api/views.py`) each open a `transaction.atomic()` block and re-read the admin count via `OrganizationMembership.objects.select_for_update().filter(...)` before deciding -- the lock covers the check. Tested on both paths: `test_last_admin_cannot_be_removed`, `test_last_admin_cannot_be_demoted`, plus triangulation (`test_non_last_admin_can_be_removed`, `test_promoting_a_member_to_admin_is_unaffected_by_the_invariant`) in `tests/integration/test_administration_invariant.py`. Not tested: true concurrent-request race (two simultaneous demotions of the last two admins) -- no thread/async concurrency test exists; the row lock's effect under real concurrency is code-verified only. |
| 8 | Analytics global aggregate is unrepresentable | COMPLIANT | `analytics/services.py:62,149,202,246` -- `environments: QuerySet[Environment]` is positional with no default value on all four `build_*` functions; calling any one with no argument is a `TypeError` at the call site, not a runtime "everything" default. `analytics/api/views.py:20-52` (`_scoped_environments`) is the sole caller and always resolves a scoped queryset first, with the malformed-UUID-vs-absent split spec'd (400 vs full-visible-scope). All 7 access-control analytics scenarios have passing tests (`tests/integration/test_analytics_api.py`, confirmed present in the 418-test run). |

### Spec Compliance Matrix (by domain)

**tenancy-model** (6 requirements / 12 scenarios) -- 6/6 requirements, 12/12 scenarios COMPLIANT. Union resolution, carve-out trap, catalogue-by-level, org admin invariant all directly tested (`tests/unit/test_capabilities.py`, `tests/unit/test_scoping.py`, `tests/integration/test_administration_invariant.py`); "Same key in two different projects" via `test_two_projects_can_each_hold_production` (`tests/unit/test_models.py:30-37`).

**access-control** (6 requirements / 16 scenarios) -- 5/6 requirements, 15/16 scenarios COMPLIANT; 1 requirement / 1 scenario UNTESTED: No Superuser Bypass (see claim #2 above). Queryset-scoping 404 requirement is compliant but unevenly proven across the 9 viewsets (see claim #1) -- recorded as a WARNING, not a scenario failure, because at least one full end-to-end instance passed and the shared mechanism is exhaustively unit-tested. Serializer FK narrowing (both scenarios), capability-gated 403, non-User-principal fail-closed (all 3 scenarios), and all 7 analytics scenarios are directly tested and passing.

**organization-management** (4 requirements / 12 scenarios) -- 4/4 requirements, 12/12 scenarios COMPLIANT. Registration auto-provisioning (`tests/integration/test_registration.py`), admin-creates-member + non-privileged-403 (`tests/integration/test_organization_members.py`), project/environment grants + rejection-without-org-membership (`tests/integration/test_role_grants.py`), all 6 seat-accounting scenarios (`tests/integration/test_organization_members.py:89-`).

**flag-management** (2 requirements / 10 scenarios) -- 2/2 requirements, 10/10 scenarios COMPLIANT. Environment Management's 6 scenarios (create/list/per-project-uniqueness/duplicate-rejected/cross-tenant-create-rejected/cross-tenant-move-rejected) all directly tested in `tests/integration/test_tenant_scoping.py:131-201` + `tests/unit/test_models.py`. Tenant-Scoped Flag CRUD's 4 scenarios covered by the FK-narrowing test family.

**Total**: 18 requirements (17 fully compliant, 1 untested-at-runtime), 50 scenarios (49 compliant, 1 untested).

### Baseline Capabilities (must be unchanged)
- `sdk-integration`, `sse-streaming`: no delta spec written for this change (correct, per proposal). `sdk_api/views.py`, `sdk_api/authentication.py`, `sdk_api/payloads.py`, `core_flags/notifications.py` confirmed byte-identical to `f3dca5b` (pre-change) via `git diff`. Baseline `openspec/specs/{sdk-integration,sse-streaming}/spec.md` files were newly written during this change (were empty before, per design F5) but describe pre-existing, unmodified behavior -- expected SDD baseline-promotion, not a functional change.

### Design Coherence
| Decision | Followed? | Notes |
|---|---|---|
| App = `tenancy/`, not `projects/`/`organizations/` | Yes | `tenancy/` app exists with 5 models, `api/{views,serializers,urls}.py` layout matching `core_flags`. |
| `resolve_capabilities` is the single source of truth | Yes | Confirmed both `capabilities_for` and the preview endpoint call it, proven equal by test (claim #5). |
| Fail-closed principal check lives in global `DEFAULT_PERMISSION_CLASSES` | Yes | `config/settings.py:195-197`: `tenancy.permissions.IsDashboardUser` is the sole global default. |
| `assert_membership_never_joined`, not `rg '\.distinct\('` | Yes | Implemented exactly as designed (`tests/conftest.py:119-132`), asserting `alias_map` disjointness. |
| Org-level role rename `OWNER`->dropped, `VIEWER`->`USER` (Engram 466/467) | Yes | `tenancy/migrations/0002_drop_organization_owner_role.py`, `0003_rename_organization_viewer_to_user.py` both present; `OrganizationRole` is `ADMIN`/`USER` only in `tenancy/models.py`. |
| Frontend `?project=` on the wire only | Yes (build-verified) | `environmentsApi.list`/`flagsApi.list` accept `project?: string` (`frontend/src/lib/api.ts`, confirmed via git history diff of PR #16/#17). |

### Known Gaps (stated plainly, per explicit instruction)

1. Zero frontend test coverage. No `*.test.ts(x)` file exists anywhere in `frontend/src`; `package.json` has no test script; CI's frontend job is named "Frontend (lint + build)" with no test step. A real regression -- `environmentsApi.create` sending `{name, key}` with no `project`, 400ing on every dashboard environment creation -- was introduced when PR #12 (`718f68c`, "enforce tenant isolation") made the field required, and survived PRs #13/#14/#15 unnoticed until PR #16 (`1ce988b`) found and fixed it while building the frontend for slice 7. Confirmed via `git log -p -- frontend/src/lib/api.ts` and the fix commit's own test `test_create_payload_without_project_is_rejected` (`tests/integration/test_tenant_scoping.py:181-201`), whose docstring names this exact history.
2. No browser was ever driven. Every frontend claim in this report (and in all prior apply-progress revisions) is machine-verified only -- TypeScript, Turbopack build, static route generation. The tenant switcher, members screen, grant dialog, effective-capability preview UI, and the org-ADMIN cascading-delete warning (confirmed present in source, `frontend/src/app/dashboard/members/page.tsx:437-440`) are unverified in actual runtime behavior.
3. Task 7.8's manual browser confirmation was never performed, and `tasks.md` says so explicitly rather than falsely claiming it -- only the automated half (`npm run lint && npm run build`) is checked.
4. No Superuser Bypass is untested at runtime (new finding this session, not previously flagged in apply-progress) -- see claim #2 above.
5. `ProjectViewSet`'s direct cross-tenant-read-404 scenario has zero end-to-end test (new finding this session) -- see claim #1 above. Very likely correct given its one-line `get_queryset` and the exhaustively-tested `projects_with` helper, but "likely correct by construction" is not the same as "a covering test passed."
6. Organization Administration Invariant's row-lock is code-verified, not concurrency-tested -- no test issues two simultaneous demote/remove requests to prove the lock actually serializes them.

### Issues Found

**CRITICAL**:
- No Superuser Bypass (spec/access-control) -- scenario "Superuser with no membership is scoped like any user" has no covering test that ran; `is_superuser`/`create_superuser` never appears in `tests/`. Code inspection shows no bypass exists, but per this skill's rule, static evidence alone does not satisfy scenario compliance.

**WARNING**:
- Queryset Scoping Returns 404 (spec/access-control) is directly HTTP-tested for only 1 of 9 viewsets (`FeatureFlagViewSet`); `ProjectViewSet` has zero direct test of this scenario (relies on unit-level `projects_with` coverage only); `OrganizationViewSet` is covered only indirectly via its `members` action.
- `test_every_registered_viewset_is_tenant_scoped` explicitly checks only 7 of the 9 spec-listed viewsets (excludes `OrganizationViewSet`/`ProjectViewSet`, which don't use `TenantScopedViewSetMixin`) -- the structural sweep's own docstring/assertion count (`checked == 7`) makes this exclusion visible rather than silent, but it means the sweep cannot catch a future regression in the 2 excluded viewsets.
- Organization Administration Invariant's `select_for_update()` row lock has no concurrency test proving it serializes two simultaneous requests.
- Zero frontend test coverage (see Known Gaps #1/#2) -- structural, not a regression introduced by this change, but load-bearing for every frontend claim in every prior apply-progress revision.

**SUGGESTION**:
- Task 7.8's manual browser confirmation remains formally open; recommend an explicit follow-up task/change if the user wants that closed before archive rather than left permanently unperformed.
- Consider adding at least one `is_superuser=True` test case to close the CRITICAL finding above cheaply (the fixture/assertion shape already exists in `test_permissions.py::TestIsDashboardUser`, which tests the `Environment`-principal case the same way).

### What Remains Unverified (explicit list)

- Any actual browser-rendered behavior of the frontend (tenant switcher, members screen, grant dialog, preview UI, nav wiring) -- build/typecheck/static-generation only.
- True concurrent-request behavior of the two `select_for_update()` row locks (org admin invariant, seat accounting).
- The "No Superuser Bypass" scenario at runtime (code-verified only).
- `ProjectViewSet`'s direct HTTP 404-on-foreign-read behavior (unit-level only).
- Production data-migration backfill behavior -- not applicable; this change ships pre-release with no existing tenant data (confirmed clean `main` history, no prior deploy of this schema).

### Verdict

**PASS WITH WARNINGS.** All 68 tasks complete and accurately checked off; 418/418 backend tests pass on Postgres; backend lint clean; frontend lint/build/typecheck clean; every load-bearing architectural claim (union resolution, join-free scoping, preview/enforcement identity, SDK byte-identity, analytics unrepresentability, org admin invariant) is directly, often exhaustively, tested. The one CRITICAL finding (no runtime test for the superuser-bypass scenario, though code inspection shows no bypass exists) and the WARNING-level uneven test depth across the 9 tenant-scoped viewsets are real, newly-identified gaps this session -- not previously surfaced in apply-progress -- that should be closed with two or three small additional tests before this change is considered fully proven, though neither reflects a broken implementation as far as static and available dynamic evidence show.
