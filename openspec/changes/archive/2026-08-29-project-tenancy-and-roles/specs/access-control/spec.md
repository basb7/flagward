# Access Control Specification

## Purpose

The three enforcement layers applied to every dashboard endpoint — queryset
scoping, serializer FK narrowing, capability-gated permission — plus the
non-`User` principal boundary and the corrected analytics scoping.

## Requirements

### Requirement: Queryset Scoping Returns 404, Not 403

Every dashboard viewset MUST scope its `get_queryset()` to objects the
requesting user can view under the tenancy model. A request for an object
outside that scope MUST return 404, never 403, so existence is never
disclosed to a user without visibility.

Applies to: `OrganizationViewSet`, `ProjectViewSet`, `EnvironmentViewSet`,
`FeatureFlagViewSet`, `StrategyRuleViewSet`, `ConditionViewSet`,
`FlagOverrideViewSet`, `SDKRegistrationViewSet`, `EvaluationLogViewSet`.

#### Scenario: Reading another organization's object returns 404

- GIVEN a user with no membership in Organization B
- WHEN the user requests GET on any object that belongs to Organization B (organization, project, environment, flag, rule, condition, override, SDK registration, or evaluation log)
- THEN the system returns 404
- AND the response does not reveal whether the object exists

#### Scenario: List endpoints never include foreign-tenant rows

- GIVEN a user visible to Environment A only
- WHEN the user lists flags, rules, conditions, or overrides
- THEN only rows scoped under Environment A are returned

### Requirement: Serializer FK Narrowing Returns 400, Not a Silent Accept

Every write endpoint accepting a parent-object FK MUST narrow that field's
queryset to objects the user holds the capability required for that write.
Submitting another tenant's UUID MUST be rejected with 400, independent of
queryset scoping on the view itself. This applies to five narrowed fields,
not four: `flag`, `rule`, and `environment` on the lower-level writes, plus
the environment's own `project` field — the root of the chain, since
`Environment` gains a writable `project` reference and is otherwise the one
object whose parent-tenant FK nothing else narrows.

#### Scenario: Cross-tenant FK write rejected

- GIVEN a user with `flag.edit` on Environment A only
- WHEN the user submits a create request referencing Environment B's UUID as the parent
- THEN the system returns 400
- AND no row is created

#### Scenario: Root-level cross-tenant write — environment created under a foreign project

- GIVEN a user holds no membership in Organization B
- WHEN the user submits a create request for an `Environment` referencing a `project` UUID that belongs to Organization B
- THEN the system returns 400
- AND no environment is created

### Requirement: Capability-Gated Actions Return 403

`HasCapability` MUST deny any action whose required capability is absent from
the user's resolved effective capability set (per union resolution), and MUST
return 403.

#### Scenario: Insufficient role denied

- GIVEN a user holds environment role `VIEWER` on Environment A (no `flag.edit`)
- WHEN the user attempts to PATCH a flag in Environment A
- THEN the system returns 403

### Requirement: No Superuser Bypass

Django's `is_superuser` flag MUST NOT grant any capability or bypass in
`HasCapability`. Superadmin operations happen exclusively through `/admin/`.

#### Scenario: Superuser with no membership is scoped like any user

- GIVEN a Django superuser with no `OrganizationMembership` anywhere
- WHEN the superuser calls any dashboard API endpoint
- THEN the system applies the same queryset scoping and capability checks as for any other user
- AND the superuser sees no tenant data without an explicit membership

### Requirement: Non-User Principal Fails Closed

The system MUST check that `request.user` is an instance of `User` before
any membership lookup runs, on every dashboard endpoint. A request
authenticated by `SDKAuthentication` (whose principal is an `Environment`,
not a `User`) MUST be rejected with 403, not raise an unhandled exception.

This check MUST be enforced through the default permission layer applied
globally, not declared per-view, so a dashboard viewset added later is
protected without its author doing anything. Placing it globally is safe for
the SDK surface: every SDK endpoint declares its own permission classes that
override the default, and the SSE stream view is a plain Django view that
never reaches this layer at all.

#### Scenario: Dashboard endpoint receives an API-key principal

- GIVEN a request carries a valid `X-API-Key` header and no user session
- WHEN the request reaches a dashboard endpoint
- THEN the system returns 403
- AND no `AttributeError` or 500 is raised

#### Scenario: A newly added viewset inherits the guard automatically

- GIVEN a new dashboard viewset is added with no explicit permission declaration of its own
- WHEN a request authenticated by `SDKAuthentication` reaches that viewset
- THEN the system returns 403
- AND no additional code was required in that viewset to achieve it

#### Scenario: SDK endpoints are unaffected by the global default

- GIVEN an SDK endpoint declares its own permission classes for API-key authentication
- WHEN an SDK sends a request with a valid API key
- THEN the request is authenticated and processed normally
- AND the global non-User-principal check does not interfere

### Requirement: Analytics Scoping Is Always Bounded

No analytics endpoint MAY return figures aggregated beyond the environments
the requesting user can view analytics on (capability `analytics.view`), with
or without query parameters.

#### Scenario: No filter scopes to the user's visible environments

- GIVEN a user can view analytics on 2 of the 50 environments in the database
- WHEN the user requests analytics with no `environment` or `project` filter
- THEN the response aggregates only those 2 environments

#### Scenario: Environment filter for an invisible environment

- GIVEN a user cannot view analytics on Environment X
- WHEN the user requests analytics with `?environment=<X>`
- THEN the system returns 404

#### Scenario: Malformed environment filter is rejected, not treated as absent

- GIVEN a user requests analytics with `?environment=not-a-uuid`
- WHEN the value cannot be parsed as a UUID
- THEN the system returns 400
- AND the request is not treated as if no filter were supplied

#### Scenario: Malformed project filter is rejected, not treated as absent

- GIVEN a user requests analytics with `?project=not-a-uuid`
- WHEN the value cannot be parsed as a UUID
- THEN the system returns 400
- AND the request is not treated as if no filter were supplied

#### Scenario: Project filter for an invisible project

- GIVEN a user cannot view analytics on any environment inside Project Y
- WHEN the user requests analytics with `?project=<Y>`
- THEN the system returns 404

#### Scenario: User with an organization but no grants

- GIVEN a user belongs to an organization but holds no project or environment membership
- WHEN the user requests analytics with no filter
- THEN the system returns 200 with zero-valued counters
- AND no error is raised

#### Scenario: Total environment count reflects scope

- GIVEN a user can view analytics on 2 of 50 environments
- WHEN the user requests the overview
- THEN `environments.total` equals 2, not the global environment count
