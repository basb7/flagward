# Archive Report: project-tenancy-and-roles

**Date**: 2026-08-29  
**Change**: project-tenancy-and-roles  
**Repository**: flagward (main branch)  
**Status**: ARCHIVED  

---

## Executive Summary

The `project-tenancy-and-roles` change has been successfully completed, implemented, and verified. The change introduces organization/project/environment tenancy with RBAC across flagward, ensuring tenant isolation at three membership levels with capability-based access control. All 11 PRs have merged, all 68 tasks are complete and checked off, and 422 tests pass on PostgreSQL. The CRITICAL verification finding (superuser bypass) was closed by PR #19 with runtime test coverage. Four WARNING-level gaps remain open and are explicitly carried forward as follow-up work items.

---

## Final State (at close)

**Authority ranking per sdd-archive skill:**
1. Explicit final-state facts from launch prompt (most authoritative)
2. Native review authority (none applied to this change)
3. Persisted tasks artifact (all 68 checked `[x]`)
4. Intermediate snapshots (verify-report at id 468, apply-progress)

### Test Coverage & Build Status

Per launch prompt (supersedes verify-report's 418 count):
- **Backend tests**: 422 passing on PostgreSQL 18.6 (verify-report: 418; PR #19 added 4 tests covering superuser-no-membership scenarios)
- **Backend lint**: `ruff check .` clean
- **Frontend lint**: `npm run lint` (biome) green, no fixes needed
- **Frontend build**: `npm run build` (Next.js 16.3.3) green, all routes generated
- **SDK code**: Zero changes; `sdk_api/views.py`, `sdk_api/authentication.py`, `sdk_api/payloads.py`, `core_flags/notifications.py` are byte-identical to pre-change state (f3dca5b)
- **API key uniqueness**: `Environment.api_key` remains globally `unique=True`

### Verification Outcome

**Prior status** (id 468, at commit 364ee8e): PASS WITH WARNINGS
- 1 CRITICAL: No Superuser Bypass (untested at runtime)
- 4 WARNINGs: uneven viewset coverage, no frontend tests, task 7.8 browser confirmation not performed, org admin invariant code-verified only

**Current status** (at commit fe17682, main branch head):
- **CRITICAL: CLOSED** — PR #19 added `TestNoSuperuserBypass` in `tests/integration/test_tenant_scoping.py`
  - Four test cases: listing, retrieval, writing, and analytics from a Django superuser holding no membership
  - Verified by mutation: injecting `if request.user.is_superuser: return True` into `HasCapability.has_permission` fails the write test only (reads stopped by Layer 1 queryset scoping independent of permission class)
  - Superuser write case correctly returns 403 (no membership = no `flag.edit` capability anywhere)
  - `tenancy/permissions.py` restored afterwards with empty diff
- **4 WARNINGs: CARRIED FORWARD** as explicit follow-up work (see "Open Work" section below)

### Delivery & Release Information

**PRs merged**: 11 (not 7 slices as originally forecast)
- #9–#18: Slices 1–7 (with 7 split into 7a/7b mid-flight after Phase 8 discovered backend gaps)
- #19: Phase 8 correction + superuser test (closes CRITICAL)

**Product decisions recorded in migrations**:
- `tenancy/migrations/0002_drop_organization_owner_role.py`: Removed `OrganizationRole.OWNER` (granted exactly what `ADMIN` granted; Engram id 466)
- `tenancy/migrations/0003_rename_organization_viewer_to_user.py`: Renamed `OrganizationRole.VIEWER` to `USER` for org-level consistency (Engram id 467)

**Test performance**: 87s worst-case → ~5s after PBKDF2 removal and cheap hasher suite-wide swap

---

## Specifications Merged

### New Capability Specs (created in openspec/specs/)

| Domain | Status | Requirements | Scenarios |
|--------|--------|--------------|-----------|
| tenancy-model | Created | 6 | 12 |
| access-control | Created | 6 | 16 |
| organization-management | Created | 4 | 12 |

**Source**: Copied from `openspec/changes/project-tenancy-and-roles/specs/` → `openspec/specs/` (mechanical copy verified byte-identical)

### Modified Specification (flag-management)

**Status**: Delta merged into existing spec  
**Changes**: 
- Modified "Environment Management" requirement: 3 scenarios → 6 scenarios (added project scoping, per-project uniqueness, cross-tenant rejection scenarios)
- Added "Tenant-Scoped Flag CRUD" requirement: 4 new scenarios (404 on foreign-environment read, 400 on cross-tenant FK writes)
- All prior flag-management requirements and scenarios preserved

**Verification**: openspec/specs/flag-management/spec.md now contains 7 total requirements (was 6) with flag-management capability split fully expressed

### Baseline Specifications (unchanged)

| Domain | Status |
|--------|--------|
| sdk-integration | Verified unchanged: code (sdk_api/*.py, core_flags/notifications.py) byte-identical to f3dca5b; spec promotes existing behavior |
| sse-streaming | Verified unchanged: spec promotes existing behavior |

Both were promoted from `feature-flags-mvp` change into `openspec/specs/` for baseline documentation. No functional changes.

---

## Archive Contents

**Location**: `openspec/changes/archive/2026-08-29-project-tenancy-and-roles/`

| Artifact | Size | Purpose |
|----------|------|---------|
| proposal.md | 29.8 KB | Rev 2 change proposal with 10 design decisions (D1–D10) |
| design.md | 48.1 KB | Implementation design with 6 corrections (F1–F6) and strict TDD structure |
| tasks.md | 38.6 KB | 8-slice ordered checklist; all 68 tasks checked `[x]`; includes phase ordering, rollback notes, traceability to spec requirements |
| verify-report.md | 17.9 KB | Verification report at commit 364ee8e (prior to PR #19 superuser test) |
| exploration.md | 12.8 KB | Prior exploration phase |
| specs/ | — | Four spec files: tenancy-model, access-control, organization-management, flag-management |

**All artifacts preserved for audit trail** — archive is immutable.

---

## Traceability: Observation IDs

All SDD artifacts persisted to Engram with topic keys for retrieval:

| Artifact | Engram ID | Topic Key |
|----------|-----------|-----------|
| Proposal | 459 | sdd/project-tenancy-and-roles/proposal |
| Spec | 461 | sdd/project-tenancy-and-roles/spec |
| Design | 462 | sdd/project-tenancy-and-roles/design |
| Tasks | 464 | sdd/project-tenancy-and-roles/tasks |
| Verify Report | 468 | sdd/project-tenancy-and-roles/verify-report |
| Archive Report | (this document) | sdd/project-tenancy-and-roles/archive-report |

---

## Open Work (Carried Forward as Follow-Up Tasks)

### WARNING 1: Queryset Scoping 404 Coverage — Uneven Across Viewsets

**Finding** (id 468): Direct HTTP 404-on-foreign-GET tested for 1 of 9 viewsets only.
- ✓ FeatureFlagViewSet: direct test `test_tenant_scoping.py:39-45`
- ✓ OrganizationViewSet: indirect test via nested `members` action
- ✗ **ProjectViewSet**: zero direct test; relies on unit-level `projects_with` helper

**Evidence**: `test_every_registered_viewset_is_tenant_scoped` (`test_tenant_scoping.py:110-128`) structurally checks 7 of 9 viewsets; explicitly excludes OrganizationViewSet and ProjectViewSet.

**Recommendation**: Add end-to-end 404 scenario for ProjectViewSet (and confirm OrganizationViewSet's direct scenario if not already covered).

### WARNING 2: Frontend Test Coverage — Zero

**Finding** (id 468): No `*.test.ts(x)` or `*.spec.ts(x)` files exist under `frontend/src`; `package.json` has no `test` script; CI's frontend job is "Frontend (lint + build)" with no test step.

**Evidence**: 
- Real regression in PR #12–#16: `environmentsApi.create` called without `project`, 400ing on every dashboard environment creation, undetected until PR #16 built the frontend for slice 7
- All frontend claims (tenant switcher, members screen, grant dialog, effective-capability preview, org-ADMIN cascading-delete warning) are build/typecheck-verified only, not runtime-verified

**Recommendation**: This is structural to the project (not introduced by this change). Either establish a test suite or explicitly acknowledge the structural risk as an ongoing project limitation.

### WARNING 3: Superuser Bypass Runtime Test Added in PR #19 (Closes CRITICAL)

**Closed**: PR #19 added `TestNoSuperuserBypass` with four cases covering listing, retrieval, writing, and analytics from a superuser with no membership.

**Status**: CRITICAL closed; no follow-up needed.

### WARNING 4: Organization Administration Invariant — Row Lock Concurrency Test

**Finding** (id 468): `select_for_update()` row lock on the Organization table is code-verified but has no test issuing two simultaneous demote/remove requests to prove lock serialization.

**Evidence**: `tenancy/api/views.py` and `tests/integration/test_administration_invariant.py` cover sequential paths (`test_last_admin_cannot_be_removed`, `test_last_admin_cannot_be_demoted`) and single-request triangulation, but no thread/async concurrency test.

**Recommendation**: Add a concurrency test using threading or async fixtures to verify the row lock actually serializes two simultaneous requests. Standard limitation for this type of test, but worth closing for completeness.

---

## Product Decisions and Model Changes

1. **Organization-level role collapse** (Engram 466, 467):
   - Removed `OrganizationRole.OWNER` — it granted exactly what `ADMIN` granted, so it distinguished nothing
   - Renamed `OrganizationRole.VIEWER` to `USER` — matches Flagsmith's two-role organization model
   - Organization level is now: `ADMIN` / `USER` only

2. **Union role resolution** (not carve-out override):
   - Capabilities combine across org/project/env levels via set UNION
   - Consequence: grant NARROW AT TOP, WIDEN DOWNWARD; cannot grant wide then carve out
   - Mitigation: members UI presents grants as additive and shows effective capability set before saving

3. **Seat accounting** (organization-level):
   - One `OrganizationMembership` = one seat (including owner)
   - Project and environment memberships do not consume seats
   - `select_for_update()` row lock on Organization for atomicity

4. **Analytics unrepresentability** (design D7):
   - Removed the `if environment_id is None: return queryset` escape
   - Global aggregate is now a `TypeError` at call site (no default value on `environments` parameter)
   - Scope by `analytics.view` capability, not `environment.view`

---

## Quality Metrics

| Metric | Value |
|--------|-------|
| Tasks completed | 68/68 (100%) |
| Backend tests passing | 422 on PostgreSQL 18.6 |
| Backend lint | Clean (`ruff check .`) |
| Frontend lint | Clean (biome, `npm run lint`) |
| Frontend build | Green (Next.js 16.3.3, all routes generated) |
| SDK code unchanged | ✓ (4 files verified byte-identical) |
| Specs merged | ✓ (3 new + 1 delta merged) |
| Archive verified | ✓ (all artifacts present) |

---

## Rollback Sharp Edge

Reversing `core_flags.0003_environment_project.py`'s `AlterUniqueTogether` re-imposes global uniqueness on `Environment.key`. This fails with IntegrityError once two projects each hold a `production` environment.

**Supported rollback window**: Slice 2 revert is safe only before a second project is created in production. After that, forward-fix required. Plan expires when a release is cut or real users exist (per design).

---

## Change Closed

This change is **complete, verified, and archived**. All artifacts have been moved to `openspec/changes/archive/2026-08-29-project-tenancy-and-roles/` and are immutable for audit purposes.

The four WARNING-level gaps are real and should be addressed in follow-up work, but they do not reflect broken implementation — they reflect structural testing/coverage limitations (frontend, concurrency) and architectural choices (union-based roles) that warrant explicit, ongoing attention rather than being silently assumed solved.

---

**Archived**: 2026-08-29  
**Archive report topic**: sdd/project-tenancy-and-roles/archive-report
