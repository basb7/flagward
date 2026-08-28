# Tenancy Model Specification

## Purpose

The `Organization → Project → Environment` hierarchy, the three membership
tables, the capability catalogue split across those three levels, and how
roles resolve into effective capabilities.

## Requirements

### Requirement: Tenancy Hierarchy

Every `Environment` MUST belong to exactly one `Project`, and every `Project`
MUST belong to exactly one `Organization`. `Environment` uniqueness MUST be
scoped to `(project, key)`, not global.

#### Scenario: Environment requires a project

- GIVEN a request to create an `Environment`
- WHEN no `project` is supplied
- THEN the system rejects the request

#### Scenario: Same key in two different projects

- GIVEN Project A and Project B, both visible to the requesting user
- WHEN each project creates an environment keyed `production`
- THEN both environments are created without conflict

### Requirement: Capability Catalogue by Level

The system MUST define capabilities at organization, project, and environment
level, each acting only on objects at or below its own level.

| Level | Capabilities |
|---|---|
| Organization | `org.view`, `org.manage_members`, `org.manage`, `org.delete`, `project.create` |
| Project | `project.view`, `project.manage`, `project.manage_members`, `project.delete`, `environment.create`, `environment.delete` |
| Environment | `environment.view`, `environment.manage`, `flag.edit`, `override.manage`, `analytics.view` |

#### Scenario: flag.edit is environment-scoped, not project-scoped

- GIVEN `FeatureFlag.environment` is a direct FK with no project-level flag definition
- WHEN the capability catalogue is evaluated
- THEN `flag.edit` grants apply per environment, not per project

### Requirement: Role to Capability Grants

Each level MUST define its own fixed roster of roles (`ADMIN`/`EDITOR`/
`OPERATOR`/`VIEWER`, plus organization-only `OWNER`), each mapped to a frozen
set of capabilities at that level, defined in code rather than a database
table.

#### Scenario: Organization OWNER is exclusive

- GIVEN an organization
- WHEN membership rows are queried
- THEN exactly one `OrganizationMembership` holds role `OWNER`

#### Scenario: Environment membership implies parent project visibility only

- GIVEN a user holds only an `EnvironmentMembership` with no `ProjectMembership`
- WHEN effective capabilities are resolved for that user
- THEN the user gains `project.view` on the environment's parent project
- AND gains no other project-level capability from that environment grant

### Requirement: Union Role Resolution

Effective capabilities on an environment MUST be the union of the
organization role's capabilities, the project role's capabilities, and the
environment role's capabilities. A missing membership at a level contributes
the empty set. No level MAY reduce a capability granted at a higher level.

#### Scenario: Organization ADMIN cannot be narrowed by a lower grant

- GIVEN a user holds organization role `ADMIN`
- AND holds no `ProjectMembership` or `EnvironmentMembership` anywhere
- WHEN effective capabilities are resolved for any project or environment in that organization
- THEN the user retains every `ADMIN` capability at every level

#### Scenario: Grants at different levels combine

- GIVEN a user holds project role `VIEWER` on Project X
- AND holds environment role `EDITOR` on environment `staging` inside Project X
- WHEN effective capabilities on `staging` are resolved
- THEN the result includes both the `VIEWER` capabilities and `flag.edit`/`override.manage` from `EDITOR`

#### Scenario: No membership at a level grants nothing extra

- GIVEN a user holds an `OrganizationMembership` with role `VIEWER`
- AND holds no `ProjectMembership` and no `EnvironmentMembership` for a given environment
- WHEN effective capabilities on that environment are resolved
- THEN only `org.view` is present

### Requirement: The Carve-Out Trap

Because resolution is a union, the system MUST NOT support subtracting or
overriding a capability granted at a higher level. To withhold a capability
that a project-level grant would otherwise provide on one specific
environment, the admin MUST grant a narrower role at project level and widen
it explicitly at the environment level that needs the extra capability.

#### Scenario: Narrow at project, widen at environment

- GIVEN an admin wants a user to edit flags in `staging` but not in `production`
- WHEN the admin grants project role `VIEWER` and adds environment role `EDITOR` on `staging` only
- THEN the user can edit flags in `staging` and cannot edit flags in `production`

#### Scenario: Wide grant plus attempted carve-out does not work

- GIVEN an admin grants project role `EDITOR` (which includes `flag.edit` on every environment in the project)
- WHEN the admin also creates an `EnvironmentMembership` with role `VIEWER` on `production`, intending to remove edit rights there
- THEN the resulting effective capabilities on `production` still include `flag.edit`, because union resolution only adds

### Requirement: Organization Ownership Invariant

The system MUST prevent an organization from ever having zero `OWNER`
memberships.

#### Scenario: Last owner cannot be removed

- GIVEN an organization has exactly one `OWNER`
- WHEN a request attempts to remove or demote that membership
- THEN the system rejects the request
