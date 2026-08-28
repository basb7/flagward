# Proposal: Organization/Project/Environment tenancy with role-based access control

## Intent

`flagward` has **no tenant isolation of any kind**. The only gate is the global
`DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` (`config/settings.py:187-189`); every
dashboard viewset ships an unscoped `queryset` (`core_flags/api/views.py:30,36,52,59,85`;
`sdk_api/api/views.py:18,28`). Any authenticated user reads and writes every other user's
environments, flags, rules, conditions and overrides. The analytics endpoints are worse:
`_scope_by_environment` is a no-op when no id is supplied (`analytics/services.py:44-48`)
and the views never require one (`analytics/api/views.py:14-16`), so the default response
aggregates the **entire database** across all tenants.

The product also has nowhere to put paid seats or owner-created users. This change
introduces the hierarchy `Organization → Project → Environment → FeatureFlag →
StrategyRule → Condition`, a three-level role→capability model with **union** semantics, and
enforcement on every dashboard read and write path.

## Scope

### In Scope

- New app with `Organization`, `Project`, and three membership tables
  (`OrganizationMembership`, `ProjectMembership`, `EnvironmentMembership`).
- Frozen role→capability map in code, split across organization / project / environment
  levels; `max_seats(plan)` with `COMMUNITY` = unlimited.
- Three enforcement layers on every dashboard endpoint: queryset scoping (404), serializer
  FK-queryset narrowing (400), `HasCapability` (403).
- Analytics rework so an unscoped aggregate becomes unrepresentable.
- Registration auto-provisions an `Organization` with the registrant as `OWNER`.
- Owner/admin module: create users, place them in the organization, grant per-project **and
  per-environment** roles.
- Shared `conftest.py` fixtures and migration of 126 inline construction sites in 11 test files.
- Postgres service added to CI.
- Frontend organization/project context, switcher, and members screen with per-environment grants.

### Out of Scope

- **The SDK surface.** `sdk_api/views.py`, `sdk_api/authentication.py`, `sdk_api/payloads.py`,
  `core_flags/notifications.py` change by zero lines. `Environment.api_key` keeps its own
  field-level `unique=True` (`core_flags/models.py:37`), independent of `Meta.unique_together`.
- Billing, invoicing, a plan-features table, or a permissions table in the database.
- Project scoping inside Django `/admin/`. Superadmin is an operations role exercised there;
  there is **no `is_superuser` bypass** in the DRF permission class.
- Invitation emails, SSO, audit log of role changes, change-request/approval workflows.
- Any per-level **deny**. Permissions only add — see D1.

## Capabilities

`openspec/specs/` now holds the baseline. The four capability specs that were stranded in
`openspec/changes/feature-flags-mvp/specs/` (`flag-management`, `flag-evaluation`,
`sdk-integration`, `sse-streaming`) were promoted on 2026-08-28 and marked Active. They were
copied, not moved, so the unarchived change folder keeps its historical record. Deltas in this
change are written against them.

### New Capabilities

- `tenancy-model`: the Organization/Project/Environment hierarchy, three membership tables,
  the three-level capability catalogue, union role resolution, plan and seat limits.
- `access-control`: the three enforcement layers, the `*_with(user, capability)` scoping
  contract, and analytics scoping.
- `organization-management`: registration auto-provisioning, owner-created users, per-project
  and per-environment role grants, seat enforcement.

### Modified Capabilities

- `flag-management`: dashboard CRUD becomes membership-scoped and capability-gated;
  `Environment` uniqueness moves from global `key` to `(project, key)`. Caveat: this spec
  lives in the `feature-flags-mvp` change folder, not `openspec/specs/`, so `sdd-spec` must
  decide whether to promote it or write the requirement into `access-control`.
- `sdk-integration`: **not modified** — listed only to record that its unchanged behavior is
  a hard acceptance criterion of this change.

## Approach

### D1 — Union role resolution, three membership levels

Role resolution is **union**, never override. Effective capabilities on an environment:

```
caps(user, env) = ORG_ROLE_CAPS[org_role]
                ∪ PROJECT_ROLE_CAPS[project_role]
                ∪ ENV_ROLE_CAPS[env_role]        # missing membership contributes ∅
```

The organization role always wins and can never be reduced further down. This matches the
reference product: Flagsmith states *"Organisation Administrators have full access to
everything, so granular permissions only apply to users with the User role"*, and combines
multiple roles as a union.

**The practical consequence, stated plainly**: under union you **grant narrow at the top and
widen downward**. You cannot grant wide and carve out. To let someone edit flags in `staging`
but not `production`, you give them project-level `VIEWER` and add environment-level `EDITOR`
on `staging` — you cannot give them project-level `EDITOR` and demote `production`. This is
the operating model the members UI must teach, or admins will build the wrong grants.

Three tables, each keeping `unique_together`:

| Table | Unique on | Meaning |
|---|---|---|
| `OrganizationMembership(organization, user, role)` | `(organization, user)` | Belonging + seat + org role |
| `ProjectMembership(project, user, role)` | `(project, user)` | Grant across every environment in one project |
| `EnvironmentMembership(environment, user, role)` | `(environment, user)` | Grant on one environment |

A third table is required, not optional: the target grant ("EDITOR on staging, OPERATOR on
production") has no expression at project level. Under union the uniqueness constraints are a
convenience, not a correctness requirement — two rows for the same `(env, user)` would simply
union. Override semantics would have made a second row ambiguous. Keeping the constraint one
row per pair keeps seat accounting and the UI simple while leaving room for a future
multi-role feature.

### D2 — The level split that fits flagward, which is not Flagsmith's

Flagsmith puts `Update feature state` at environment level because a Flagsmith `Feature`
belongs to a **Project** and each environment holds a separate `FeatureState`. The definition
is shared; only the state is per-environment.

**flagward has no such split.** `FeatureFlag.environment` is a direct FK
(`core_flags/models.py:54`) with `Meta.unique_together = ("environment", "key")` (line 66).
Each environment owns its own flags outright. `StrategyRule.flag` (line 76) and
`Condition.rule` (line 94) hang below, so targeting is per-environment too;
`FlagOverride.flag` (line 130), `SDKRegistration.environment` (`sdk_api/models.py:21`) and
`EvaluationLog.flag` (`:56`) likewise.

So flagward's `flag.edit` is **already structurally environment-scoped**, and Flagsmith's
project/environment boundary does not transfer. Copying it verbatim would put "create/delete
feature" at project level, where flagward has no project-level feature to create. The split
that actually fits is: **a capability lives at the level of the object it acts on.**

| Level | Capability | Acts on |
|---|---|---|
| Organization | `org.view` | The organization, its plan, own membership |
| | `org.manage_members` | Create users, org memberships, org roles — consumes seats |
| | `org.manage` | Rename, change plan |
| | `org.delete` | The organization |
| | `project.create` | New `Project` rows in the org |
| Project | `project.view` | The project and its environment list |
| | `project.manage` | Rename |
| | `project.manage_members` | Grant project- and environment-level roles inside it |
| | `project.delete` | The project |
| | `environment.create` / `environment.delete` | `Environment` rows in the project |
| Environment | `environment.view` | The environment |
| | `environment.manage` | Rename, rotate `api_key` |
| | `flag.edit` | `FeatureFlag`, `StrategyRule`, `Condition` |
| | `override.manage` | `FlagOverride` — create and lift |
| | `analytics.view` | `SDKRegistration`, `EvaluationLog`, analytics aggregates |

Every capability settled earlier (`project.view`, `project.manage_members`, `project.delete`,
`environment.manage`, `flag.edit`, `override.manage`) keeps its name and gains a level.

### D3 — `flag.edit` vs `override.manage` still earns its place

Both now live at environment level, so the question is whether the pair is still doing work.
It is, and the split is **destructive vs. auditable**, not project vs. environment:

| | `flag.edit` | `override.manage` |
|---|---|---|
| Can delete a flag and its rules | Yes | No |
| Can rewrite targeting silently | Yes | No |
| Leaves a trail | No | Yes — rows are never deleted; `lift()` stamps `cleared_at` (`models.py:152-157`) |
| Requires a written reason | No | Yes — `reason = models.TextField()` (`:132`), no `blank=True` |
| Reversible to the configured state | No | Yes — lifting restores it (`:119-128`) |

An `OPERATOR` on `production` can mitigate an incident with a mandatory reason and a full
audit trail, and cannot destroy configuration. An `EDITOR` on `production` can flip
`is_enabled` with no trail at all. That is a genuine separation of duty, so both capabilities
stay. Keeping only one would force the choice between "on-call cannot mitigate" and "on-call
can delete production flags untraceably".

### D4 — Roles under union semantics

Same five names, defined per level. `OWNER` is organization-only: there is one owner of an
organization, tied to seats and plan; a "project owner" would be a second ownership concept
with no billing meaning.

**Organization** — the base role is `VIEWER`; this is Flagsmith's "User" role, the one
granular permissions exist for.

| Role | Grants |
|---|---|
| `OWNER` | Every capability at every level, org-wide. Exactly one per org (the registrant); last-owner guard on removal and demotion |
| `ADMIN` | Everything org-wide except `org.manage` and `org.delete` |
| `VIEWER` | `org.view` only — sees nothing else until granted below |

**Project** — grants apply to every environment in that project.

| Role | Grants |
|---|---|
| `ADMIN` | All project capabilities + all environment capabilities in this project |
| `EDITOR` | `project.view`, `environment.view`, `flag.edit`, `override.manage`, `analytics.view` |
| `OPERATOR` | `project.view`, `environment.view`, `override.manage`, `analytics.view` |
| `VIEWER` | `project.view`, `environment.view`, `analytics.view` |

**Environment** — grants apply to that one environment.

| Role | Grants |
|---|---|
| `ADMIN` | `environment.view`, `environment.manage`, `flag.edit`, `override.manage`, `analytics.view` |
| `EDITOR` | `environment.view`, `flag.edit`, `override.manage`, `analytics.view` |
| `OPERATOR` | `environment.view`, `override.manage`, `analytics.view` |
| `VIEWER` | `environment.view`, `analytics.view` |

Shape: three frozen dicts `{role: frozenset[capability]}`, inverted once at import into
`{capability: frozenset[role]}` for the query path. No database table, no seeding, no drift.

**Narrow implication**: holding any `EnvironmentMembership` also grants `project.view` on that
environment's parent project — otherwise the user can see an environment while its project is
invisible and the UI cannot navigate to it. This implication is scoped to `project.view` and
nothing else; it must not carry any other project capability.

### D5 — Scoping under three levels: the fan-out returns, then is designed out

The coordinator was right to ask. Visibility of an environment now has three sources, so the
naive filter is a three-way `OR` and the join fan-out is worse than at two levels. Written
with a membership join, `Q(memberships__user=u) | Q(project__in=...)` still fans out: the
second branch is row-independent, so **every** joined membership row satisfies the `WHERE` and
an environment with `n` memberships returns `n` duplicates.

The fix generalizes the v1 trick until no multi-valued join survives anywhere.

**Invariant: a membership relation is never traversed as a join in a filter. Every membership
lookup is a `values()` subquery consumed by `__in`.**

```
orgs_with(u, cap)     = OrganizationMembership.objects
                          .filter(user=u, role__in=ORG_ROLES_GRANTING[cap])
                          .values("organization_id")

projects_with(u, cap) = Project.objects.filter(
                            Q(organization__in=orgs_with(u, cap))
                          | Q(pk__in=ProjectMembership.objects
                                .filter(user=u, role__in=PROJECT_ROLES_GRANTING[cap])
                                .values("project_id")))

environments_with(u, cap) = Environment.objects.filter(
                            Q(project__in=projects_with(u, cap))
                          | Q(pk__in=EnvironmentMembership.objects
                                .filter(user=u, role__in=ENV_ROLES_GRANTING[cap])
                                .values("environment_id")))
```

Both branches of each `OR` are scalar predicates on the model's own columns (`organization_id`
/ `pk`, `project_id` / `pk`). **No join appears in any branch, so nothing fans out at any
level.** This is strictly better than the v1 design, where `visible_projects` used
`Q(memberships__user=u)` — a real join — and therefore needed `.distinct()` when serialized.

**`.distinct()` is now needed nowhere in this change**, including on the helpers themselves.
That is a testable rule, not a claim: `rg '\.distinct\(' ` over the new code must return
nothing. The `(tenant, user)` uniqueness of all three membership tables is preserved, but it
is no longer what the correctness argument rests on — the absence of joins is.

Visibility is just a capability: `visible_environments(u) ≡ environments_with(u,
"environment.view")`. One function serves queryset scoping, serializer narrowing and the
permission class.

Cost: three nested `IN` subqueries. Postgres flattens these into semi-joins. Add an explicit
index on `user_id` in all three membership tables — `unique_together` indexes lead with the
tenant column, but every one of these subqueries filters on `user` first.

### D6 — Scoping filter path

Let `E = environments_with(u, "environment.view")`, `P = projects_with(u, "project.view")`.
Chains are one hop **shorter** than in v1, because they now terminate at `environment`.

| ViewSet | File:line | `get_queryset()` |
|---|---|---|
| `OrganizationViewSet` | new | `pk__in=orgs_with(u, "org.view")` |
| `ProjectViewSet` | new | returns `P` |
| `EnvironmentViewSet` | `core_flags/api/views.py:28` | returns `E` |
| `FeatureFlagViewSet` | `:34` | `environment__in=E` |
| `StrategyRuleViewSet` | `:50` | `flag__environment__in=E` |
| `ConditionViewSet` | `:57` | `rule__flag__environment__in=E` |
| `FlagOverrideViewSet` | `:64` | `flag__environment__in=E` |
| `SDKRegistrationViewSet` | `sdk_api/api/views.py:15` | `environment__in=E` |
| `EvaluationLogViewSet` | `:25` | `flag__environment__in=E` |

Layer 2 narrows each write-side FK by the **capability that write requires**. The permission
class has no object to inspect on `POST`, so the serializer queryset is the only create-time
gate — and it is now capability-precise per environment:

| Serializer | Field | Narrowed to |
|---|---|---|
| `FeatureFlagSerializer` (`serializers.py:49`) | `environment` | `environments_with(u, "flag.edit")` |
| `StrategyRuleSerializer` (`:31`) | `flag` | `FeatureFlag.objects.filter(environment__in=environments_with(u, "flag.edit"))` |
| `ConditionSerializer` (`:23`) | `rule` | `StrategyRule.objects.filter(flag__environment__in=environments_with(u, "flag.edit"))` |
| `FlagOverrideSerializer` (`:94`) | `flag` | `FeatureFlag.objects.filter(environment__in=environments_with(u, "override.manage"))` |

This is where environment-level granularity actually bites: an `OPERATOR` on `production` and
`EDITOR` on `staging` gets two different FK querysets on the same request path. Layer 2 was
already non-redundant with layer 1; with three levels it is the only layer that can express
this.

`perform_create` (`views.py:108`) reads `serializer.validated_data["flag"]` with no ownership
check; the narrowed queryset closes it before that line runs.

**Hazard, found while verifying and not in the exploration.** `SDKAuthentication` is
registered **globally** (`config/settings.py:185`) and returns an `Environment` instance as
`request.user` (`sdk_api/authentication.py:31`). A dashboard request bearing `X-API-Key`
therefore reaches the permission layer with a non-`User` principal. `Environment` is a plain
`models.Model` (`core_flags/models.py:32`) and defines no `is_authenticated`, so DRF's
`IsAuthenticated` raises `AttributeError` — a 500 today, not a data leak. The point stands:
`HasCapability` must fail closed on an explicit `isinstance(request.user, User)` check before
any membership lookup, rather than relying on that accident.

### D7 — Analytics: make the unscoped call unrepresentable

Delete `_scope_by_environment`'s `if environment_id is None: return queryset` escape
(`analytics/services.py:46-47`). The four `build_*` functions stop taking
`environment_id: uuid.UUID | None` and take a resolved, already-scoped `QuerySet[Environment]`,
so no caller can reach a global aggregate even by mistake.

| Request | Behavior |
|---|---|
| `?environment=<uuid>` | 404 unless it resolves inside `environments_with(u, "analytics.view")` |
| `?project=<uuid>` (new) | 404 unless visible; scope to that project's visible environments |
| Neither | Scope to every environment the user can read analytics on — not the global table |
| User with an org but no grants | `200` with zero-valued counters. Empty state, not an error |

Scoping uses `analytics.view`, not `environment.view`: they are granted together by every role
today, but the capability the endpoint requires is the one it should check.
`environments.total` (`services.py:115-118`) must use the same scoped count; today it calls
`Environment.objects.count()` outright. The four `@api_view` functions get explicit
`permission_classes`; they have none today (`analytics/api/views.py:19,26,36,47`).

### D8 — Seat counting

A seat is **one `OrganizationMembership` row**, owner included. Not project or environment
memberships (a user across five projects and ten environments is one seat) and not global
`auth.User` rows.

| Case | Behavior |
|---|---|
| Boundary | Create allowed while `count() < max_seats`; the row that would exceed it is rejected `400 seat_limit_reached`. A plan of N holds N members including the owner |
| `COMMUNITY` | `max_seats` returns `None`; the check short-circuits |
| Member removed | Seat freed immediately — the row is gone |
| `User.is_active = False` | Seat **still consumed**; the membership row still exists |
| Plan downgraded below current count | Existing members keep access; new memberships refused until the count drops. No auto-eviction |
| Concurrent adds | `select_for_update()` on the `Organization` row inside the creating transaction |

Invariant: a `ProjectMembership` or `EnvironmentMembership` may only exist for a user who
already holds an `OrganizationMembership` in that object's organization. Without it, seat
counting is a lie and a grant can outlive the membership that paid for it.

### D9 — Slicing

The exploration's ~1050-1600 estimate predates `Organization`; the previous revision's
~2175-2930 predates environment-level granularity. Re-estimated at **seven slices**:

| # | Slice | Contents | Lines |
|---|---|---|---|
| 1 | Postgres in CI | `services:` block + env in `.github/workflows/ci.yml`; independent, no product change | 25-40 |
| 2 | Schema + test fixtures | `Organization`, `Project`, 3 membership tables, admin, **one** consolidated migration, `conftest.py`, 11 test files migrated | 640-790 |
| 3 | Capability model | 3-level catalogue, 3 role dicts + inverted lookup, `orgs_with`/`projects_with`/`environments_with`, `HasCapability`, union-resolution unit tests. Pure library code, no viewset wiring | 320-430 |
| 4 | Enforcement wiring | 9 viewsets + 4 serializers + integration tests | 480-640 |
| 5 | Analytics | Service signature change, 4 views, permissions, tests | 350-500 |
| 6 | Org & member management | Registration auto-provisioning, org/project/**environment** grant CRUD, seat enforcement, tests | 570-760 |
| 7 | Frontend | `api.ts`, org/project context + switcher, ~6 dashboard pages, members screen with per-environment grants | 420-560 |
| | **Total** | | **2805-3720** |

Slice 3 is new and exists precisely to keep slice 4 under budget: the capability model is
independently testable without touching a single viewset, and separating it means the
enforcement PR is a wiring review rather than a wiring-plus-semantics review.

Every slice lands under the 800-line budget. Two are tight:

- **Slice 2 (790)** cannot be split. `Environment.project` becoming `NOT NULL` breaks all 126
  construction sites at `setup_method`, so the migration and the fixture rewrite must land
  together or CI is red between PRs. If it overruns, it is the one legitimate
  `size:exception` candidate.
- **Slice 6 (760)** *can* be split if it overruns — organization member management first,
  then project/environment grant CRUD — because the two share no schema.

Strategy: **Feature Branch Chain** with a draft tracker. Slice 1 goes straight to `main` — it
is independent and should land first so every later migration is exercised on the production
engine. Slices 2-7 chain behind the tracker, because each intermediate state is incoherent on
`main`: slice 2 alone ships unenforced tenancy tables, and slice 4 without slice 6 locks every
self-registered user out of everything.

```
main ──▶ PR1 (Postgres CI)
main ──▶ tracker (draft) ──▶ PR2 ──▶ PR3 ──▶ PR4 ──▶ PR5 ──▶ PR6 ──▶ PR7
```

Guard lines for `sdd-tasks`:

```
Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High
```

### D10 — Test infrastructure

Its own **work unit**, but **not its own PR** — fused into slice 2 for the CI reason above. No
`conftest.py` exists anywhere in the repo. New fixtures: `organization`, `project`,
`environment`, `flag`, plus a role-parameterized `api_client` for the capability matrix. That
matrix is now three-dimensional (level × role × capability), which is most of slice 3's and
slice 4's test cost — and the union resolver is exactly the kind of thing a table-driven test
covers cheaply, so parameterize rather than enumerate.

Note `tests/integration/test_admin_api.py:27-127` are `pass` stubs that assert nothing but
still build rows in `setup_method`, so they contribute diff noise for no coverage; converting
them is optional and should be an explicit call, not a silent drive-by.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `organizations/` (new app) | New | `Organization`, `Project`, 3 membership tables, capability catalogue, role dicts, `*_with()` helpers, `HasCapability`, `max_seats` |
| `core_flags/models.py:32-40` | Modified | `Environment.project` FK; `unique_together` `("key",)` → `("project","key")` |
| `core_flags/api/views.py` | Modified | 5 viewsets: `get_queryset` + `permission_classes` |
| `core_flags/api/serializers.py` | Modified | 4 FK querysets narrowed per request, per capability |
| `analytics/services.py` + `analytics/api/views.py` | Modified | Scope becomes mandatory; permissions added |
| `sdk_api/api/views.py` | Modified | 2 viewsets scoped |
| `sdk_api/` (SDK surface) | **Unchanged** | Hard constraint; verified in exploration |
| `authentication/views.py:105-160` | Modified | Registration auto-provisions org + OWNER |
| `core/management/commands/create_super_user.py` | Unchanged | Superadmin works via `/admin/`; no bypass, no auto-membership |
| `tests/` (11 files, 126 sites) + new `conftest.py` | Modified/New | Fixture layer |
| `.github/workflows/ci.yml` | Modified | Postgres service |
| `frontend/src/lib/api.ts`, `frontend/src/app/dashboard/*` | Modified | Org/project context, switcher, members screen with per-environment grants |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Admins build the wrong grants because union cannot carve out | **High** | The members UI must present grants as additive and show the resolved effective capability set per environment before saving |
| A future `OR` branch is written as a join, silently reintroducing fan-out | Med | One test asserts `.distinct()` appears nowhere; helpers are the only sanctioned membership query path |
| Non-`User` principal (`Environment` via global `SDKAuthentication`) reaching the membership layer | Med | `HasCapability` fails closed on `isinstance(request.user, User)`; explicit test |
| A scoped queryset is missed on a viewset added later | Med | Base `TenantScopedViewSet` that raises unless a scope chain is declared; no bare `queryset = Model.objects.all()` survives review |
| Serializer narrowing forgotten on a new FK | Med | Shared serializer mixin + one cross-cutting test asserting every write FK is narrowed |
| Three nested `IN` subqueries per request | Low | Explicit `user_id` index on all three membership tables; Postgres flattens `IN (SELECT ...)` to semi-joins |
| SQLite/Postgres divergence on the `unique_together` alter | Med | Slice 1 lands Postgres in CI **before** the migration slice |
| Slice 2 overruns the 800-line budget | Med | Accept `size:exception` for that slice only; splitting it leaves CI red |

## Rollback Plan

Correction retained: `openspec/config.yaml` has **no** `rules:` section — all 73 lines read;
the keys are `project`, `context`, `strict_tdd`, `testing`, `frontend_testing`, `phases`. The
exploration's citation of a config rule requiring a rollback plan is wrong. The `sdd-propose`
skill mandates one regardless.

| Slice | Rollback |
|---|---|
| 1 | `git revert`. No product impact |
| 3, 4, 5, 6, 7 | `git revert`. Code-only; restores the previous (insecure) behavior |
| 2 | `migrate core_flags <previous>` then `migrate <newapp> zero` — now drops **five** tables, not three. `RunPython` reverse is a no-op, safe **only** because the project is pre-release |

**Made safer by these decisions**: because the capability map is a frozen dict in code rather
than a database table, reverting a slice reverts the permission semantics atomically with the
code. There is no seeded permission data to roll back separately or to drift out of sync with
a partially reverted deployment. Under union semantics a partial revert can only ever *widen*
access, never leave a user holding a grant that means something different from what the code
now says — override semantics would have made a half-reverted state genuinely ambiguous.

**The one sharp edge, unchanged**: reversing `AlterUniqueTogether` re-imposes global uniqueness
on `Environment.key`. If by rollback time two projects each hold a `production` environment,
the reverse migration **fails**. Rolling slice 2 back is therefore supported only before a
second project exists; after that the supported path is forward-fix, not revert. Whole-feature
rollback means reverting the tracker merge and recreating data — acceptable only while
pre-release holds (no released version, no real users). This plan expires the moment either
becomes false.

## Dependencies

- Postgres available in CI (slice 1) before the migration slice merges.
- Pre-release status holds — no release cut, no real users. Every rollback above assumes it.
- Existing migration history is preserved, not squashed: `sdk_api.0001` depends on
  `core_flags.0001`.

## Success Criteria

- [ ] A user cannot read or write any object outside `environments_with(u, cap)` for the
      capability that action requires — 404 on read, 400 on a cross-tenant FK write, 403 on a
      capability they lack.
- [ ] A user holding project `VIEWER` plus environment `EDITOR` on `staging` and environment
      `OPERATOR` on `production` can edit flags in `staging`, cannot edit flags in
      `production`, and can fire the kill switch in both.
- [ ] An organization `ADMIN` retains every capability in every project and environment
      regardless of any lower-level membership row — no grant can reduce it.
- [ ] No analytics endpoint returns a figure spanning more than one organization, with or
      without query parameters.
- [ ] Adding the member that would exceed `max_seats(plan)` returns `400 seat_limit_reached`;
      `COMMUNITY` never does.
- [ ] Registering a new user yields exactly one `Organization` with that user as `OWNER`.
- [ ] Two projects can each own an environment keyed `production`.
- [ ] SDK integration tests pass with zero changes to `sdk_api/views.py`,
      `sdk_api/authentication.py`, `sdk_api/payloads.py`, `core_flags/notifications.py`.
- [ ] A dashboard request bearing `X-API-Key` is rejected by `HasCapability`, not by an
      `AttributeError`.
- [ ] `pytest` green on Postgres in CI; `ruff check .` clean.
- [ ] `.distinct()` appears nowhere in the change.

## Settled inputs

Recorded so later phases do not reopen them: `Organization → Project → Environment` hierarchy;
no `is_superuser` bypass in the DRF permission class; open self-registration with an
auto-created `Organization`; seats on `Organization`; capability map as a frozen dict in code
rather than a database table; three enforcement layers; `api_key` untouched and zero SDK code
changes; one consolidated migration; Postgres added to CI; **union role resolution**;
**environment-level capability granularity**.
