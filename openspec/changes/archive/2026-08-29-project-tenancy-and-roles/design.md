# Design: Organization/Project/Environment tenancy with role-based access control

## Technical Approach

One new Django app, `tenancy/`, owns the hierarchy (`Organization`, `Project`), the three
membership tables, the frozen capability catalogue, the scoping helpers, the permission class
and the serializer mixin. Every other app consumes it and never re-implements it.

The whole change rests on **one pure function**, `resolve_capabilities(org_role, project_role,
env_role) -> frozenset[str]`, which touches no database. Three things are derived from it and
proven equal to it by test: per-object permission checks, set-valued queryset scoping, and the
UI's "what will this grant actually do" preview. Anything that duplicates the capability map —
a database table, a TypeScript copy, a hand-written `if role == "ADMIN"` — is rejected, because
drift between the preview and the enforcement is exactly the top risk the proposal names.

> **Size note.** This document exceeds `sdd-design`'s 800-word budget. The orchestrator
> enumerated ten mandatory deliverables (model layout with every constraint, nine queryset
> expressions, four analytics signatures, the migration operation list, the CI diff, frontend
> architecture). Prose is compressed to tables and the snippets below are load-bearing, but the
> budget and the brief cannot both be honoured. Recorded as a deliberate deviation, not an
> oversight.

---

## Findings: where the proposal does not survive contact with the code

Read this section first. Each item changes what `sdd-tasks` must plan.

### F1 — "One consolidated migration" is impossible. It is two files.

`migrations.AddField` takes its `app_label` from the migration that contains it, so a field on
`core_flags.Environment` cannot be added from a `tenancy` migration. The tenancy tables cannot
be created from a `core_flags` migration either. The change needs **two** files:

| File | Contents |
|---|---|
| `tenancy/migrations/0001_initial.py` | 5 `CreateModel` |
| `core_flags/migrations/0003_environment_project.py` | `AddField` → `RunPython` → `AlterField` → `AlterUniqueTogether` |

What the proposal actually meant — *no split across deploys, no nullable window shipped to
production* — is fully preserved: both files land in the same commit and the same `migrate` run.
The dependency graph is linear, **not** circular: `core_flags.0002` → `tenancy.0001` (needs
`Environment` for `EnvironmentMembership`) → `core_flags.0003` (needs `Project`). Verified
against `core_flags/migrations/0002_alter_featureflag_options_alter_flagoverride_options_and_more.py`
and `sdk_api/migrations/0001_initial.py`'s existing dependency on `core_flags.0001`.

### F2 — The test churn is 44 sites, not 126. And 82 of the 126 need no change at all.

Measured, not estimated:

| Pattern | Count | Breaks on NOT NULL `project`? |
|---|---|---|
| `Environment.objects.create(...)` | **44** across 11 files | Yes — needs `project=` |
| `FeatureFlag.objects.create(environment=env, ...)` | **82** across 9 files | **No** — receives an already-built `Environment` |

`tests/unit/test_models.py` alone holds 23 of the 44. Adoption mechanics: 18 `setup_method`
blocks across 8 files cannot receive pytest fixtures, so each becomes
`@pytest.fixture(autouse=True) def _setup(self, project):` — a two-line conversion with an
unchanged body. Six module-level fixtures in 3 files gain a `project` parameter. Real touched
surface is roughly **70 lines**, not the 126-site rewrite slice 2 was sized against. Slice 2's
790-line forecast should come down and its `size:exception` is probably unnecessary.

### F3 — The Layer-2 table is missing a serializer, and it is the one that matters most.

The proposal narrows four FKs. `EnvironmentSerializer` (`core_flags/api/serializers.py:15-20`)
gains a `project` write field and is a **fifth**. Without narrowing it, any authenticated user
can `POST /api/v1/environments/` with another organization's project UUID and plant an
environment inside a tenant they do not belong to — the root-level version of the exact hole
this change exists to close. It must be narrowed to
`projects_with(u, Capability.ENVIRONMENT_CREATE)`.

Related: `api_key` is `read_only` (`serializers.py:20`), so `environment.manage`'s "rotate
api_key" cannot be a field write. It is a `@action(detail=True, methods=["post"])
def rotate_api_key` on `EnvironmentViewSet`.

### F4 — Analytics silently widens scope on a malformed UUID, inconsistently with the rest of the API.

`parse_uuid` returns `None` for anything unparseable (`analytics/services.py:25-32`), and
`analytics/api/views.py:14-16` feeds that straight through. So `?environment=oops` is treated as
"no filter". Post-change that is no longer a cross-tenant leak, but it answers a different
question than the one asked and reports it as success. Meanwhile `QueryParamFilterMixin` raises
400 for the same input everywhere else (`core/api/mixins.py:62-65`). **Decision: present but
unparseable → 400.** Absent → the full visible scope.

### F5 — `openspec/specs/` is no longer empty.

The proposal states it is (line 50). Four baseline specs are now promoted:
`flag-management`, `flag-evaluation`, `sdk-integration`, `sse-streaming`. The parallel
`sdd-spec` phase deltas against those. No design impact; recorded so nobody re-litigates it.

### F6 — Swapping the global permission default is safe. Verified, not assumed.

Every SDK endpoint declares its own `@permission_classes([IsSDKAuthenticated])`
(`sdk_api/views.py:30,45,90`), and `sdk_stream` is a **plain Django async view**
(`async def sdk_stream(request)`, `sdk_api/views.py:128`) that resolves the api_key itself at
lines 140-149 and never reaches DRF's permission layer at all. Changing
`DEFAULT_PERMISSION_CLASSES` therefore cannot touch the SDK surface. This is what makes the
fail-closed guard in D5 placeable globally instead of per-view.

---

## Architecture Decisions

### D1 — App name and layout: `tenancy/`

| Option | Tradeoff | Decision |
|---|---|---|
| `projects/` (orchestrator's working assumption) | Names one of five models; `Organization` is the root, not `Project` | Rejected |
| `organizations/` (proposal) | Names the root model but not the membership/capability half | Rejected |
| Two apps (`tenancy` + `access_control`) | Cleaner layering, but a second migration graph node for zero runtime benefit | Rejected |
| **`tenancy/`** | Names the concern, not a model; matches the proposal's own `tenancy-model` / `access-control` capability names; matches how `core_flags` is named after a concern rather than after `FeatureFlag` | **Chosen** |

Layout follows the repo's `<app>/api/{views,serializers,urls}.py` convention (`core_flags`,
`analytics`, `sdk_api`). `authentication/` is the outlier that keeps `views.py` at app root —
not followed here, and not fixed here either.

```
tenancy/
  models.py       Organization, Project, 3 membership tables, Plan, 3 Role enums
  capabilities.py Capability constants, 3 role→caps dicts, inverted maps, resolve_capabilities, max_seats
  scoping.py      orgs_with / projects_with / environments_with / capabilities_for
  permissions.py  IsDashboardUser, HasCapability, TenantScopedViewSetMixin
  serializers.py  CapabilityScopedFKMixin        (library-level, imported by core_flags/api)
  admin.py
  migrations/0001_initial.py
  api/{views,serializers,urls}.py
```

`core/` stays dependency-free — the shared-base app must not learn about capabilities, so
`core/api/mixins.py` is not where any of this goes despite being the repo's precedent for shared
DRF mixins.

### D2 — Model layout

Every model uses `UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`, matching
all five existing models (`core_flags/models.py:34,53,75,93,129`) rather than the
`BigAutoField` default at `config/settings.py:169`. Membership rows are addressable in URLs
(`DELETE /api/v1/organization-members/{id}/`), and sequential ids there would make organization
size enumerable.

**`tenancy/models.py`**

| Model | Fields | Constraints & indexes |
|---|---|---|
| `Organization` | `id`, `name` `CharField(255)`, `plan` `CharField(20, choices=Plan.choices, default=COMMUNITY)`, `created_at` `DateTimeField(auto_now_add=True)` | — |
| `Project` | `id`, `organization` `FK(Organization, CASCADE, related_name="projects")`, `name` `CharField(255)`, `key` `SlugField(255)`, `created_at` | `UniqueConstraint(["organization","key"], name="unique_project_key_per_organization")` |
| `OrganizationMembership` | `id`, `organization` `FK(CASCADE, related_name="memberships")`, `user` `FK(AUTH_USER_MODEL, CASCADE, related_name="organization_memberships")`, `role` `CharField(20, choices=OrganizationRole.choices)`, `created_at` | `UniqueConstraint(["organization","user"], name="unique_organization_membership")`; `Index(["user"], name="orgmembership_user_idx")`; `CheckConstraint(condition=Q(role__in=OrganizationRole.values), name="orgmembership_role_valid")` |
| `ProjectMembership` | same shape, `project` `FK(Project, CASCADE, related_name="memberships")`, `role` `choices=ProjectRole.choices` | `unique_project_membership`; `projectmembership_user_idx`; `projectmembership_role_valid` |
| `EnvironmentMembership` | same shape, `environment` `FK("core_flags.Environment", CASCADE, related_name="memberships")`, `role` `choices=EnvironmentRole.choices` | `unique_environment_membership`; `envmembership_user_idx`; `envmembership_role_valid` |

**`core_flags/models.py`** — `Environment` gains
`project = models.ForeignKey("tenancy.Project", on_delete=models.CASCADE, related_name="environments")`
and `Meta.unique_together` moves from `("key",)` (line 40) to `("project", "key")`.
`api_key` keeps its own field-level `unique=True` (line 37), untouched — that is the hard
constraint that keeps the SDK at zero changes.

Both cross-app FKs use **lazy string references** (`"tenancy.Project"`,
`"core_flags.Environment"`), so neither `models.py` imports the other and there is no Python
import cycle to work around.

**Three role enums, not one.** `OrganizationRole(ADMIN, USER)`,
`ProjectRole(ADMIN, EDITOR, OPERATOR, VIEWER)`, `EnvironmentRole(ADMIN, EDITOR, OPERATOR,
VIEWER)`. A single shared enum would let the database hold `role="OWNER"` on a
`ProjectMembership`, which the capability map maps to ∅ — a grant that looks maximal in the
admin and grants nothing. Separate enums make it unrepresentable in the type; the
`CheckConstraint` makes it unrepresentable in the database.

**`unique_together` vs `UniqueConstraint`.** New tables use named `UniqueConstraint`, following
the repo's newest precedent (`sdk_api/models.py:38-42`) — named constraints produce readable
`IntegrityError` messages, which the duplicate-grant and seat tests assert against.
`Environment` keeps `unique_together`: converting its style would turn one
`AlterUniqueTogether` into `AlterUniqueTogether(set())` + `AddConstraint`, and the reverse into
two operations carrying the same sharp edge. Style migration is an orthogonal refactor.

### D3 — The capability resolver

Three layers, each derived from the one above it:

```python
# capabilities.py — pure, no database, no request, no user object
def resolve_capabilities(
    org_role: str | None,
    project_role: str | None,
    env_role: str | None,
) -> frozenset[str]:
    caps = (
        ORG_ROLE_CAPS.get(org_role, EMPTY)
        | PROJECT_ROLE_CAPS.get(project_role, EMPTY)
        | ENV_ROLE_CAPS.get(env_role, EMPTY)
    )
    # D4's narrow implication: any environment grant makes the parent project
    # navigable, and grants nothing else about it.
    if env_role is not None:
        caps = caps | {Capability.PROJECT_VIEW}
    return caps
```

```python
# scoping.py
def capabilities_for(user: User, environment: Environment) -> frozenset[str]   # 3 queries
def orgs_with(user: User, capability: str) -> QuerySet[Organization]
def projects_with(user: User, capability: str) -> QuerySet[Project]
def environments_with(user: User, capability: str) -> QuerySet[Environment]
```

**Unknown capability strings raise.** `capability not in ALL_CAPABILITIES` → `ValueError`, never
a silent empty set. A typo that silently denies is a 403 nobody can debug; worse, the same typo
on the write path silently *narrows nothing* and the mismatch ships. The inverted maps use
`.get(cap, frozenset())` only for *known* capabilities that simply do not exist at that level
(`org.view` asked of `ENV_ROLES_GRANTING`), which is a legitimate empty answer.

**Three consumers, one source:**

| Consumer | Call | Shape |
|---|---|---|
| Queryset scoping | `environments_with(u, ENVIRONMENT_VIEW)` | set-valued, one subquery |
| Serializer FK narrowing | `environments_with(u, FLAG_EDIT)` | set-valued, one subquery |
| `HasCapability.has_object_permission` | `cap in capabilities_for(u, env)` | per-object |
| Frontend grant preview | `resolve_capabilities(...)` on *proposed* roles | pure, no persistence |

**The consistency invariant, and its test.** These two shapes must never disagree. For every
environment `E` and every capability `c`:

```
c ∈ resolve_capabilities(org_role, project_role, env_role)   ⟺   E ∈ environments_with(u, c)
```

`4 × 5 × 5 = 100` role tuples (including "no membership" at each level), each asserting the full
15-capability set matches. This is the table-driven test D10 asked for, and it is what makes the
UI preview provably identical to enforcement.

### D4 — Join-free scoping, and how the invariant is enforced

```python
def orgs_with(user, capability):
    _check_known(capability)
    return Organization.objects.filter(
        pk__in=OrganizationMembership.objects
            .filter(user=user, role__in=ORG_ROLES_GRANTING.get(capability, EMPTY))
            .values("organization_id"))

def projects_with(user, capability):
    _check_known(capability)
    predicate = (
        Q(organization__in=orgs_with(user, capability).values("pk"))
        | Q(pk__in=ProjectMembership.objects
              .filter(user=user, role__in=PROJECT_ROLES_GRANTING.get(capability, EMPTY))
              .values("project_id")))
    if capability == Capability.PROJECT_VIEW:
        # Mirrors resolve_capabilities' narrow implication. Still a scalar
        # subquery, so the no-join invariant survives it.
        predicate |= Q(pk__in=Environment.objects.filter(
            pk__in=EnvironmentMembership.objects.filter(user=user).values("environment_id")
        ).values("project_id"))
    return Project.objects.filter(predicate)

def environments_with(user, capability):
    _check_known(capability)
    return Environment.objects.filter(
        Q(project__in=projects_with(user, capability).values("pk"))
        | Q(pk__in=EnvironmentMembership.objects
              .filter(user=user, role__in=ENV_ROLES_GRANTING.get(capability, EMPTY))
              .values("environment_id")))
```

Every `OR` branch is a scalar predicate on the model's own column. No membership relation is
traversed as a join, so nothing fans out and `.distinct()` is needed nowhere.

**The nine viewsets.** `E = environments_with(u, ENVIRONMENT_VIEW)`:

| ViewSet | File:line | Scope |
|---|---|---|
| `OrganizationViewSet` | new | `orgs_with(u, ORG_VIEW)` |
| `ProjectViewSet` | new | `projects_with(u, PROJECT_VIEW)` |
| `EnvironmentViewSet` | `core_flags/api/views.py:28` | `Environment.objects.filter(pk__in=E)` |
| `FeatureFlagViewSet` | `:34` | `.filter(environment__in=E)` |
| `StrategyRuleViewSet` | `:50` | `.filter(flag__environment__in=E)` |
| `ConditionViewSet` | `:57` | `.filter(rule__flag__environment__in=E)` |
| `FlagOverrideViewSet` | `:64` | `.filter(flag__environment__in=E)` |
| `SDKRegistrationViewSet` | `sdk_api/api/views.py:15` | `.filter(environment__in=E)` |
| `EvaluationLogViewSet` | `:25` | `.filter(flag__environment__in=E)` |

**MRO gotcha, verified.** `QueryParamFilterMixin.get_queryset` calls `super().get_queryset()`
(`core/api/mixins.py:51-52`), and `FlagOverrideViewSet` already defines its own `get_queryset`
that also calls `super()` (`core_flags/api/views.py:94-95`). A class-body `get_queryset` shadows
any mixin. Declaration order must therefore be
`class X(TenantScopedViewSetMixin, QueryParamFilterMixin, ModelViewSet)`, and
`FlagOverrideViewSet`'s existing override keeps working because it calls `super()` first.
Filters compose with `AND`, so ordering within the chain is correctness-neutral — but the
shadowing is not, and a viewset that defines `get_queryset` without calling `super()` silently
loses tenant scoping. That is a review item and a test (below).

#### How the invariant is enforced against future contributors

The proposal proposes `rg '\.distinct\('` must find nothing. **Rejected.** Reasons:

- It tests the absence of a *symptom*, not the invariant. A contributor can reintroduce a
  fan-out join and simply not add `.distinct()`; the grep stays green and the API starts
  returning duplicate rows.
- False negatives are trivial (`.distinct ()`, `getattr(qs, "distinct")()`, a `.distinct()` on
  an unrelated line of a values query).
- False positives are guaranteed the first time someone legitimately needs `.distinct()` in
  code that has nothing to do with membership, and the fix will be to weaken the test.

**Chosen instead:** assert the property directly through Django's own query API.

```python
# tests/conftest.py
MEMBERSHIP_TABLES = frozenset({
    OrganizationMembership._meta.db_table,
    ProjectMembership._meta.db_table,
    EnvironmentMembership._meta.db_table,
})

def assert_membership_never_joined(queryset):
    """The scoping invariant, asserted rather than grepped."""
    # alias_map holds only the OUTER query's tables; subqueries live in the
    # where-tree and never appear here. A membership table showing up means
    # somebody wrote a join.
    assert MEMBERSHIP_TABLES.isdisjoint(queryset.query.alias_map), queryset.query.alias_map
    # And nobody masked a fan-out by adding distinct().
    assert queryset.query.distinct is False
```

Applied by a parameterized test over the three helpers × every capability, plus every registered
viewset's `get_queryset()`. It permits `select_related("environment")`
(`core_flags/api/views.py:36`) — which *is* a join and is fine — while forbidding the one join
class that actually fans out.

Backed by a second, engine-independent behavioural test: give one user an org membership, a
project membership and an environment membership that all grant the same capability on the same
environment, then assert `environments_with(u, cap).count() == 1`. Fan-out would return 3. The
pair is airtight — the behavioural test proves no duplication, the structural test proves it was
not achieved by masking with `distinct()`.

**Third guard, for the "somebody adds a viewset and forgets" risk:** a test that walks the DRF
routers in `core_flags/api/urls.py` and `sdk_api/api/urls.py`, asserting every registered
viewset subclasses `TenantScopedViewSetMixin` and declares `environment_lookup`, against an
explicit allowlist. `TenantScopedViewSetMixin` raises `ImproperlyConfigured` when
`environment_lookup` is left at its `_UNSET` sentinel, so the failure is loud at first request
rather than a silently unscoped `Model.objects.all()`.

### D5 — The three enforcement layers, and the fail-closed principal

| Layer | Mechanism | Failure | Status |
|---|---|---|---|
| 1 — Queryset scoping | `TenantScopedViewSetMixin.get_queryset()` | Object outside `environments_with(u, ENVIRONMENT_VIEW)` is not in the queryset, so `get_object()` raises `Http404` | **404** |
| 2 — Serializer FK narrowing | `CapabilityScopedFKMixin.get_fields()` | `PrimaryKeyRelatedField` cannot resolve the pk → `ValidationError` | **400** |
| 3 — `HasCapability` | `has_object_permission` / `has_permission` | Object visible but the action's capability is absent | **403** |

Layer 2 is the **only** create-time gate: DRF has no object on `POST`, so
`has_object_permission` never runs and Layer 3 cannot express "which environment". It closes
`FlagOverrideViewSet.perform_create`, which reads `serializer.validated_data["flag"]` with no
ownership check (`core_flags/api/views.py:106-114`) — the narrowed queryset rejects the pk
before line 108 executes.

**Narrowed FKs (five, not four — see F3):**

| Serializer | Field | Narrowed to |
|---|---|---|
| `EnvironmentSerializer` (`serializers.py:15`) | `project` **(new)** | `projects_with(u, ENVIRONMENT_CREATE)` |
| `FeatureFlagSerializer` (`:49`) | `environment` | `environments_with(u, FLAG_EDIT)` |
| `StrategyRuleSerializer` (`:31`) | `flag` | `FeatureFlag.objects.filter(environment__in=environments_with(u, FLAG_EDIT))` |
| `ConditionSerializer` (`:23`) | `rule` | `StrategyRule.objects.filter(flag__environment__in=environments_with(u, FLAG_EDIT))` |
| `FlagOverrideSerializer` (`:94`) | `flag` | `FeatureFlag.objects.filter(environment__in=environments_with(u, OVERRIDE_MANAGE))` |

**How the serializer gets the user, and what happens without a request.**

```python
class CapabilityScopedFKMixin:
    capability_scoped_fields: dict[str, tuple[str, Callable]] = {}

    def get_fields(self):
        fields = super().get_fields()
        user = self._scoping_user()
        for name, (capability, build) in self.capability_scoped_fields.items():
            fields[name].queryset = (
                build(user, capability) if user is not None
                else fields[name].queryset.none()
            )
        return fields

    def _scoping_user(self):
        user = getattr(self.context.get("request"), "user", None)
        return user if isinstance(user, User) else None
```

DRF injects `request` into `context` from `GenericAPIView.get_serializer_context()`; every path
through the nine viewsets has it.

Without a request — or with a non-`User` principal — the queryset becomes **`.none()`**, not
`Model.objects.all()` and not an exception.

| Option | Tradeoff | Decision |
|---|---|---|
| Leave unnarrowed | A serializer instantiated outside a request (management command, nested write, a test) silently gets `objects.all()` — the exact hole being closed | Rejected |
| Raise | Correct for writes, but breaks legitimate **read-only** use: `FeatureFlagSerializer(flag).data` outside a request would blow up | Rejected |
| **`.none()`** | Fail-closed. Reads are unaffected because `PrimaryKeyRelatedField.to_representation` reads `value.pk` and never consults the queryset; writes fail with DRF's standard "Invalid pk" 400 | **Chosen** |

Debuggability cost of the silent `.none()` is paid with a `logger.warning` and two explicit
tests: one that a write without request context 400s, one that a read without request context
still serializes correctly.

**The `SDKAuthentication` fail-closed check.** `SDKAuthentication` is registered globally
(`config/settings.py:185`) and returns `(environment, api_key)` (`sdk_api/authentication.py:31`),
so `request.user` can be an `Environment` on any dashboard route. `Environment` is a plain
`models.Model` (`core_flags/models.py:32`) with no `is_authenticated`, so `IsAuthenticated`
raises `AttributeError` today — a 500, not a leak, but a 500 nobody can read.

**Where the guard lives: the global default.** `config/settings.py:187-189` changes from
`rest_framework.permissions.IsAuthenticated` to `tenancy.permissions.IsDashboardUser`:

```python
class IsDashboardUser(BasePermission):
    """A dashboard route requires a Django User, never an api-key principal."""
    def has_permission(self, request, view):
        return isinstance(request.user, User) and request.user.is_authenticated
```

This is the only placement that cannot be forgotten per-view: it covers the nine viewsets, the
four analytics `@api_view` functions that have no `permission_classes` today
(`analytics/api/views.py:19,26,36,47`), and every view added later. F6 verifies it cannot break
the SDK: all three SDK `@api_view`s declare `@permission_classes([IsSDKAuthenticated])`
(`sdk_api/views.py:30,45,90`) and `sdk_stream` is a plain Django async view
(`sdk_api/views.py:128`) outside DRF entirely. `authentication/views.py:164,181` also move from
`IsAuthenticated` to `IsDashboardUser`, since `/auth/me/` with an `X-API-Key` header 500s today
for the same reason.

Result: `X-API-Key` on a dashboard route returns **403**, per the proposal's acceptance
criterion, from a named class rather than from an `AttributeError`.

**`HasCapability`:**

```python
class HasCapability(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True                      # Layer 1 already scoped the read
        capability = view.capability_for_action(view.action)
        return environments_with(request.user, capability).exists()

    def has_object_permission(self, request, view, obj):
        capability = view.capability_for_action(view.action)
        return capability in capabilities_for(request.user, view.environment_of(obj))
```

The unsafe-method `has_permission` check answers "could this user hold this capability
anywhere". A user who holds it nowhere gets a clean 403 on `POST` instead of a confusing 400
about an invalid pk. `capabilities_for` costs three queries plus `environment.project`, so
scoped viewsets add `select_related("environment__project")` where the chain allows.

### D6 — Migration

**`tenancy/migrations/0001_initial.py`** — `dependencies = [("core_flags", "0002_alter_featureflag_options_alter_flagoverride_options_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]`, five `CreateModel` operations with the constraints and indexes from D2. Reverse: automatic (drops five tables).

**`core_flags/migrations/0003_environment_project.py`** — `dependencies = [("core_flags", "0002_..."), ("tenancy", "0001_initial")]`:

```python
operations = [
    migrations.AddField(
        model_name="environment",
        name="project",
        field=models.ForeignKey(null=True, on_delete=models.CASCADE,
                                related_name="environments", to="tenancy.project"),
    ),
    migrations.RunPython(backfill_default_project, migrations.RunPython.noop),
    migrations.AlterField(
        model_name="environment",
        name="project",
        field=models.ForeignKey(on_delete=models.CASCADE,
                                related_name="environments", to="tenancy.project"),
    ),
    migrations.AlterUniqueTogether(name="environment", unique_together={("project", "key")}),
]
```

`backfill_default_project` is trivial because the project is pre-release: if any `Environment`
has `project_id IS NULL`, create one `Organization(name="Default", plan=COMMUNITY)` and one
`Project(name="Default", key="default")` inside it, then assign every null row to it. It creates
**no membership rows** — `compose.yml:60-63` runs `migrate` *before* `create_super_user`, so on a
fresh boot there is no `User` to attribute anything to, and a migration that assumed one would
fail. Existing deployments get a Default project with no members; a human grants ownership
through the admin.

Reverse is `RunPython.noop`, which is correct rather than lazy: reverse order runs the
`RunPython` reverse *before* `AddField` drops the column, and dropping the column removes the
assignment anyway. The Default rows disappear with `migrate tenancy zero`.

**Migration history is not reset**, per the proposal's dependency: `sdk_api/migrations/0001_initial.py` depends on `core_flags.0001`, so squashing `core_flags` would drag `sdk_api` in for nothing.

**The sharp edge, restated precisely.** Reversing `AlterUniqueTogether` re-imposes global
uniqueness on `Environment.key`. Once two projects each hold a `production` environment, the
reverse **fails with an `IntegrityError`** — and the failure modes differ by engine: Postgres
does `ALTER TABLE ... ADD CONSTRAINT` and fails on validation; SQLite rebuilds the table via
Django's `_remake_table` and fails on the insert into the new table, with a different message
and a partially different transactional shape. That divergence is the whole reason slice 1 lands
Postgres in CI first. Slice-2 revert is supported **only before a second project exists**; after
that the supported path is forward-fix.

Minor: `AlterField` to NOT NULL is a `SET NOT NULL` on Postgres, which requires a full table
scan and an `ACCESS EXCLUSIVE` lock. Irrelevant at pre-release table sizes; recorded so it is
not rediscovered at scale.

### D7 — Test infrastructure

**`tests/conftest.py`** (not repo root — `tests/` is already a package with `__init__.py`, and
`pyproject.toml` already sets `DJANGO_SETTINGS_MODULE`).

All fixtures are **function-scoped**. Session or module scope would need
`django_db_setup`/`django_db_blocker` gymnastics to survive pytest-django's per-test transaction
rollback, and would leak rows between the 170 existing tests. 44 extra inserts per run is not a
cost worth that.

| Fixture | Returns | Notes |
|---|---|---|
| `organization` | `Organization` | `plan=COMMUNITY` |
| `project` | `Project` | in `organization` |
| `environment` | `Environment` | `key="prod"`, in `project` — the drop-in for the 44 sites |
| `flag` | `FeatureFlag` | in `environment` |
| `make_project` / `make_environment` / `make_flag` | callables | for tests needing two tenants |
| `user` | `User` | no memberships |
| `grant` | callable `(user, *, org=None, project=None, environment=None, role)` | builds membership rows |
| `api_client` | callable `(user) -> APIClient` | replaces the ad-hoc `client` fixtures in 3 files |
| `assert_membership_never_joined` | helper | D4's structural guard |

**Adoption (F2).** 18 `setup_method` blocks → `@pytest.fixture(autouse=True) def _setup(self, project):` with an unchanged body plus `project=project` on the `Environment.objects.create` call. 6 module-level fixtures gain a `project` parameter. 44 `Environment.objects.create` calls gain one kwarg. The 82 `FeatureFlag.objects.create(environment=...)` calls are untouched.

**Rejected:** giving `Environment.project` a `default=` callable so the existing calls keep
working. It would resolve in production too, silently attaching environments to an arbitrary
project — it makes the NOT NULL constraint decorative and hides exactly the bug this change
exists to prevent.

`tests/integration/test_admin_api.py:27-127` are `pass` stubs whose `setup_method` still builds
rows. Their `setup_method` gets converted like the rest (they must not fail at setup), but the
bodies stay `pass`. Converting them into real tests is a separate, explicit decision.

**Strict TDD — what is RED before any implementation:**

| Order | RED test | Fails because |
|---|---|---|
| 1 | `resolve_capabilities` table: 100 role tuples × full capability set | `capabilities.py` does not exist |
| 2 | Union: org `ADMIN` + project `VIEWER` → still holds `FLAG_EDIT` | same |
| 3 | Narrow implication: env membership alone yields `PROJECT_VIEW` and nothing else at project level | same |
| 4 | `environments_with` ⟺ `resolve_capabilities` consistency | `scoping.py` does not exist |
| 5 | `assert_membership_never_joined` over the three helpers | same |
| 6 | Triple-membership fan-out: `.count() == 1` | same |
| 7 | Two projects each hold `production` | `unique_together` is still `("key",)` |
| 8 | `Environment.objects.create` without `project` raises `IntegrityError` | column is nullable / absent |
| 9 | Cross-tenant read → 404; cross-tenant FK `POST` → 400; missing capability → 403 | no enforcement wired |
| 10 | `X-API-Key` on `/api/v1/flags/` → 403 | global default is still `IsAuthenticated` |
| 11 | Every routed viewset is tenant-scoped | mixin does not exist |
| 12 | Analytics with no params spans only the user's environments | `build_*` still take `environment_id` |

Tests 1-6 belong to slice 3 and pass with zero viewset changes — that is what keeps slice 4 a
wiring review.

### D8 — Analytics

```python
# analytics/services.py
def build_overview(environments: QuerySet[Environment]) -> dict[str, Any]
def build_evaluations_timeseries(environments: QuerySet[Environment], hours: int = 24) -> dict[str, Any]
def build_top_flags(environments: QuerySet[Environment], hours: int = 24, limit: int = 5) -> dict[str, Any]
def build_sdk_health(environments: QuerySet[Environment]) -> dict[str, Any]
```

`environments` is **first and has no default**. The global aggregate stops being a thing you can
forget to prevent and becomes a `TypeError` at the call site.

`_scope_by_environment` (`services.py:44-48`) and its `if environment_id is None: return
queryset` escape are deleted, replaced by:

```python
def _scope(queryset: QuerySet, environments: QuerySet[Environment], lookup: str) -> QuerySet:
    return queryset.filter(**{f"{lookup}__in": environments.values("pk")})
```

`.values("pk")` is explicit rather than relying on Django's implicit pk coercion for `__in`,
because the caller's queryset may carry `select_related`.

Call-site edits: `services.py:64` (`FeatureFlag`, `"environment"`), `:88-90` (`SDKRegistration`,
`"environment"`), `:96-98` (`EvaluationLog`, `"flag__environment"`), `:106-108` (`FlagOverride`,
`"flag__environment"`), `:167-171`, `:215-219`, `:254-256`. The `if environment_id is None:
environments_total = Environment.objects.count()` branch (`:115-118`) collapses to
`environments.count()`.

**Queryset resolution in `analytics/api/views.py`.** `_environment_id` (`:14-16`) is replaced by:

```python
def _scoped_environments(request):
    visible = environments_with(request.user, Capability.ANALYTICS_VIEW)

    raw_env = request.query_params.get("environment")
    if raw_env:
        environment_id = services.parse_uuid(raw_env)
        if environment_id is None:
            raise ValidationError({"environment": "Not a valid UUID."})   # F4 → 400
        scoped = visible.filter(pk=environment_id)
        if not scoped.exists():
            raise NotFound()                                             # 404, no existence oracle
        return scoped

    raw_project = request.query_params.get("project")
    if raw_project:
        project_id = services.parse_uuid(raw_project)
        if project_id is None:
            raise ValidationError({"project": "Not a valid UUID."})
        if not projects_with(request.user, Capability.PROJECT_VIEW).filter(pk=project_id).exists():
            raise NotFound()
        return visible.filter(project_id=project_id)

    return visible          # every environment the user can read analytics on
```

Scoping uses `ANALYTICS_VIEW`, not `ENVIRONMENT_VIEW` — every role grants them together today,
but the endpoint should check the capability it actually requires, so a future role that splits
them does not silently leak. A user with an organization and no grants gets `200` with zeroed
counters: an empty state, not an error.

All four `@api_view` functions gain `@permission_classes([IsDashboardUser])`; they have none
today (`:19,26,36,47`). The global default from D5 already covers them, but declaring it locally
survives a future change to the default.

### D9 — Postgres in CI

`.github/workflows/ci.yml`, `backend` job only. `psycopg2-binary>=2.9,<3.0` is already in
`requirements/base.txt:7`, so no dependency change:

```yaml
  backend:
    name: Backend (lint + tests)
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_DB: flagward
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DB_NAME: flagward
      DB_USER: postgres
      DB_PASSWORD: postgres
      DB_HOST: localhost
      DB_PORT: '5432'
```

`config/settings.py:94` branches on `os.getenv('DB_NAME') or os.getenv('USE_POSTGRES')`, so
setting `DB_NAME` at job level is what flips the engine. The `frontend` job is untouched. Job
name `Backend (lint + tests)` is preserved — it is the branch-protection contract.

Setting `env` at job level also applies during `ruff check .`, which does not care. pytest-django
creates `test_flagward`; the `postgres` superuser has `CREATEDB`.

### D10 — Frontend

`TenantProvider` nests **inside** `AuthProvider` in `frontend/src/app/dashboard/layout.tsx:46-50`
— it needs `user` before it can load organizations.

**State shape** (`frontend/src/lib/tenant-context.tsx`, modelled on `auth-context.tsx`):
`{ organizations, projects, currentOrganization, currentProject, setCurrentProject, isLoading }`.

| Option | Tradeoff | Decision |
|---|---|---|
| Nested routes `/dashboard/[projectId]/...` | Moves all 6 pages down a level and rewrites every `Link`/`router.push` | Rejected (exploration already priced this) |
| `?project=` in the **app's own** URLs | Shareable, but every navigation in 6 pages must forward the param | Rejected |
| **Context + `localStorage`, `?project=` on the wire only** | Selection survives reload, no navigation changes, one place to read it | **Chosen** |

**API threading** follows `analyticsApi`'s existing `buildQuery` pattern
(`frontend/src/lib/api.ts:536-558`, `buildQuery` at `:140-152`) rather than inventing a second
convention. `environmentsApi.list(page = 1)` (`:206-209`) and `flagsApi.list(page = 1)`
(`:269-270`) currently take a bare page number; both become
`list(params: { page?: number; project?: string } = {})`. `analyticsApi`'s four functions gain
`project?: string` alongside the existing `environment?: string`.

Backend support for `?project=`: `EnvironmentViewSet` gains `QueryParamFilterMixin` (it has none
today, `core_flags/api/views.py:28-31`) with `filter_fields = ("project",)`.
`FeatureFlagViewSet.filter_fields` (`:46`) converts from tuple to the dict form
`QueryParamFilterMixin` already supports (`core/api/mixins.py:33-36`) to add
`"project": "environment__project"`. Because tenant scoping is `AND`ed first, `?project=` with
another tenant's UUID returns an **empty page, not a 404** — no existence oracle.

**Members module** (`frontend/src/app/dashboard/members/page.tsx` + `dashboard-nav.tsx` entry):
one screen per organization listing members, their org role, and their project/environment
grants as an additive list. Grants render as "adds …", never as toggles — a checkbox grid
implies you can uncheck, and under union you cannot.

**The effective-capability preview** — the mitigation for the proposal's top risk:

```
POST /api/v1/tenancy/effective-capabilities/preview/
{ "user": 7, "organization": "...", "organization_role": "USER",
  "project_roles":     { "<project-uuid>": "VIEWER" },
  "environment_roles": { "<staging-uuid>": "EDITOR", "<prod-uuid>": "OPERATOR" } }

200 { "environments": [ { "id": "...", "key": "staging",
                          "capabilities": ["environment.view","flag.edit",
                                           "override.manage","analytics.view"] }, ... ] }
```

It takes the **proposed, unsaved** roles from the body and answers through
`resolve_capabilities` — the same pure function enforcement uses. Requires
`project.manage_members` on every project referenced.

| Option | Tradeoff | Decision |
|---|---|---|
| Port the capability dicts to TypeScript | Zero round-trip, but two copies of the permission model drifting apart — the exact reason the proposal rejected a database table | Rejected |
| Save, then read back the resolved set | No duplication, but the admin has already granted the wrong thing | Rejected |
| **Server-side preview over `resolve_capabilities`** | One round-trip per edit; provably identical to enforcement because it is literally the same function | **Chosen** |

The UI shows a per-environment diff — "gains `flag.edit` on staging", "gains nothing new on
production" — before the save button is enabled. That is what teaches the grant-narrow-then-widen
model the proposal says admins will otherwise get wrong.

**Next.js note:** `frontend/AGENTS.md` warns this Next.js version differs from training data.
The apply phase must read `frontend/node_modules/next/dist/docs/` before writing any component.

---

## Data Flow

```
Dashboard request (JWT cookie)
  │
  ├─ JWTAuthenticationCookie ──▶ request.user = User
  │  SDKAuthentication       ──▶ request.user = Environment   ✗ IsDashboardUser → 403
  │
  ├─ Layer 1  TenantScopedViewSetMixin.get_queryset()
  │             .filter(<chain>__in = environments_with(u, ENVIRONMENT_VIEW))
  │             miss ──▶ 404
  │
  ├─ Layer 3  HasCapability.has_object_permission
  │             capabilities_for(u, env) ──▶ resolve_capabilities(org, proj, env roles)
  │             miss ──▶ 403
  │
  └─ Layer 2  CapabilityScopedFKMixin.get_fields()   [writes only]
                field.queryset = environments_with(u, <action capability>)
                miss ──▶ 400

resolve_capabilities  ──┬──▶ capabilities_for        (Layer 3)
   (pure, no DB)        ├──▶ *_ROLES_GRANTING ──▶ environments_with (Layers 1 & 2)
                        └──▶ /effective-capabilities/preview/  (frontend affordance)
                             ▲
                             └── one function: preview cannot drift from enforcement
```

---

## File Changes

| File | Action | Description |
|---|---|---|
| `tenancy/models.py` | Create | `Organization`, `Project`, 3 membership tables, `Plan`, 3 role enums |
| `tenancy/capabilities.py` | Create | 15 capability constants, 3 role→caps dicts, inverted maps, `resolve_capabilities`, `max_seats` |
| `tenancy/scoping.py` | Create | `orgs_with`, `projects_with`, `environments_with`, `capabilities_for` |
| `tenancy/permissions.py` | Create | `IsDashboardUser`, `HasCapability`, `TenantScopedViewSetMixin` |
| `tenancy/serializers.py` | Create | `CapabilityScopedFKMixin` |
| `tenancy/admin.py` | Create | Register all five models |
| `tenancy/api/{views,serializers,urls}.py` | Create | Org/project/member/grant CRUD, seats, preview endpoint |
| `tenancy/migrations/0001_initial.py` | Create | 5 `CreateModel` |
| `core_flags/migrations/0003_environment_project.py` | Create | `AddField` → `RunPython` → `AlterField` → `AlterUniqueTogether` |
| `core_flags/models.py:32-40` | Modify | `Environment.project` FK; `unique_together` → `("project","key")` |
| `core_flags/api/views.py` | Modify | 5 viewsets: mixin, `environment_lookup`, capability map, `rotate_api_key` action |
| `core_flags/api/serializers.py` | Modify | 4 narrowed FKs + `EnvironmentSerializer.project` (F3) |
| `sdk_api/api/views.py` | Modify | 2 viewsets scoped |
| `analytics/services.py:44-300` | Modify | `_scope_by_environment` → `_scope`; 4 signatures take `QuerySet[Environment]` |
| `analytics/api/views.py` | Modify | `_environment_id` → `_scoped_environments`; permissions |
| `authentication/views.py:105-160,164,181` | Modify | Registration auto-provisions org + `OWNER`; `IsDashboardUser` |
| `config/settings.py:187-189` | Modify | Global default → `tenancy.permissions.IsDashboardUser` |
| `config/settings.py:INSTALLED_APPS` | Modify | Add `tenancy` |
| `config/urls.py` | Modify | Mount `tenancy.api.urls` |
| `tests/conftest.py` | Create | Fixture layer + `assert_membership_never_joined` |
| `tests/**` (11 files) | Modify | 44 kwargs, 18 `setup_method` conversions, 6 fixture params |
| `.github/workflows/ci.yml` | Modify | Postgres service + `DB_*` env on the backend job |
| `frontend/src/lib/api.ts` | Modify | `project` param on environments/flags/analytics; tenancy + members API |
| `frontend/src/lib/tenant-context.tsx` | Create | Org/project context + `localStorage` persistence |
| `frontend/src/components/layout/dashboard-nav.tsx` | Modify | Org/project switcher, Members entry |
| `frontend/src/app/dashboard/layout.tsx` | Modify | `TenantProvider` inside `AuthProvider` |
| `frontend/src/app/dashboard/members/page.tsx` | Create | Grants UI + effective-capability preview |
| `frontend/src/app/dashboard/{page,environments,flags,flags/[id]/rules,monitoring}` | Modify | Read `currentProject`, pass `project` |
| `sdk_api/views.py`, `sdk_api/authentication.py`, `sdk_api/payloads.py`, `core_flags/notifications.py` | **Unchanged** | Hard constraint; verified in F6 |

---

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | `resolve_capabilities` union semantics | Parameterized over 100 role tuples, asserting the full capability set |
| Unit | Narrow implication scoped to `project.view` only | Env membership alone → assert exactly one project capability |
| Unit | `capability not in ALL_CAPABILITIES` raises | `pytest.raises(ValueError)` on all three helpers |
| Unit | No-join invariant | `assert_membership_never_joined` over helpers × capabilities |
| Unit | No fan-out | Triple membership on one env → `.count() == 1` |
| Unit | `max_seats` boundary, `COMMUNITY` unlimited | Table-driven |
| Integration | 404 / 400 / 403 split | Two tenants; read, cross-tenant FK write, capability-less write |
| Integration | The success-criterion grant | project `VIEWER` + env `EDITOR` staging + env `OPERATOR` prod: edit staging ✓, edit prod ✗, override both ✓ |
| Integration | Org `ADMIN` irreducible | Add every lower-level `VIEWER` row; capabilities unchanged |
| Integration | `X-API-Key` on a dashboard route → 403 | Assert status **and** that no `AttributeError` was raised |
| Integration | Analytics scope | No params, `?environment=`, `?project=`, foreign UUID → 404, malformed → 400, no grants → 200 zeros |
| Integration | Serializer without request context | Write → 400; read → serializes |
| Integration | Router coverage | Walk `router.registry`; every viewset tenant-scoped |
| Integration | SDK regression | Existing SDK tests pass with zero source changes to the four protected files |
| Migration | `unique_together` change | Two projects each create `production`; run on Postgres in CI |
| Frontend | Preview matches enforcement | Compare the preview response against the capability set observed after saving the same grant |

---

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary. The change alters DRF permission and queryset boundaries, which
are covered by the enforcement tests above rather than by the shell/process threat matrix.

---

## Migration / Rollout

Slice order is unchanged from the proposal's D9, with one correction and one adjustment:

1. **Slice 1 — Postgres in CI** → straight to `main`. Must land first so every later migration is exercised on the production engine.
2. **Slices 2-7** chain behind a draft tracker. Slice 2's migration is **two files, one commit, one `migrate` run** (F1).
3. Slice 2's forecast should be revised **down** from 640-790: the churn is 44 sites plus 18 conversions, not 126 (F2). The `size:exception` it was reserved for is likely unnecessary.
4. Slice 4 gains one file over the proposal's plan: `EnvironmentSerializer.project` (F3).

Rollback is unchanged and still assumes pre-release. The sharp edge is D6's:
reversing `AlterUniqueTogether` fails the moment two projects each hold a `production`
environment, with engine-dependent failure modes.

---

## Open Questions

- [ ] `Plan` values beyond `COMMUNITY`. This design assumes `COMMUNITY / STARTER / TEAM` with
      `max_seats = {COMMUNITY: None, STARTER: 5, TEAM: 25}`. The names and numbers are product
      decisions, not code facts; the shape (`frozen dict[str, int | None]`) is settled.
- [ ] `tests/integration/test_admin_api.py:27-127` stubs: convert to real tests inside slice 2,
      or leave as `pass` with only their `setup_method` fixed? This design assumes the latter to
      keep the slice-2 diff honest.
- [ ] Whether `Organization.name` needs a uniqueness constraint. Nothing in the change requires
      it; open in case the members UI wants stable display names.
