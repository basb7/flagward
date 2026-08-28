# Delta for Flag Management

## MODIFIED Requirements

### Requirement: Environment Management

The system MUST support creating and managing environments with unique API
keys, each environment belonging to exactly one project, with key uniqueness
scoped to `(project, key)` rather than global.

(Previously: environment uniqueness was global on `key` alone, and creation
required no project or capability check.)

#### Scenario: Create environment

- GIVEN an authenticated user holding `environment.create` on a project
- WHEN POST /api/v1/environments/ with project_id, name and key
- THEN system creates environment with UUID and generated api_key
- AND api_key is unique and indexed

#### Scenario: List environments

- GIVEN an authenticated user with visibility into a subset of environments
- WHEN GET /api/v1/environments/
- THEN system returns only the environments the user can view, with id, name, key, api_key

#### Scenario: Environment key uniqueness is per project

- GIVEN Project A has an environment keyed "production"
- WHEN Project B creates an environment also keyed "production"
- THEN both environments are created without conflict

#### Scenario: Duplicate key within the same project rejected

- GIVEN a project already has an environment keyed "production"
- WHEN creating a second environment in the same project with key "production"
- THEN system returns 400 error indicating key already exists

#### Scenario: Cross-tenant environment creation rejected

- GIVEN a user without `environment.create` on Project B
- WHEN the user submits a create request referencing Project B's UUID as the parent project
- THEN system returns 400 and no row is created

#### Scenario: Moving an environment into another tenant's project rejected

- GIVEN a user holds `environment.manage` on Environment E inside Project A only
- WHEN the user submits a PATCH on Environment E setting `project` to Project B's UUID
- THEN system returns 400
- AND Environment E's project assignment is unchanged

## ADDED Requirements

### Requirement: Tenant-Scoped Flag CRUD

The system MUST scope reads of `FeatureFlag`, `StrategyRule`, `Condition`,
and `FlagOverride` to environments the requesting user can view, and MUST
reject any write whose parent-object reference (environment, flag, or rule)
resolves outside the capability-scoped set for that write.

#### Scenario: Read a flag in an invisible environment

- GIVEN a user cannot view Environment B
- WHEN the user requests GET on a flag that belongs to Environment B
- THEN system returns 404

#### Scenario: Create a strategy rule referencing a foreign flag

- GIVEN a user holds `flag.edit` on Environment A only
- WHEN POST /api/v1/rules/ references a `flag_id` that belongs to Environment B
- THEN system returns 400 and no rule is created

#### Scenario: Create a condition referencing a foreign rule

- GIVEN a user holds `flag.edit` on Environment A only
- WHEN POST /api/v1/conditions/ references a `rule_id` whose flag belongs to Environment B
- THEN system returns 400 and no condition is created

#### Scenario: Create an override referencing a foreign flag

- GIVEN a user holds `override.manage` on Environment A only
- WHEN POST to the overrides endpoint references a `flag_id` that belongs to Environment B
- THEN system returns 400 and no override is created
