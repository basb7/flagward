# Flag Management Specification

**Date**: 2026-08-26
**Capability**: flag-management
**Status**: Active
**Promoted from**: changes/feature-flags-mvp (2026-08-28)

## Purpose

CRUD operations for environments, feature flags, strategy rules, and conditions. This is the core data model for the feature flag system.

## Requirements

### Requirement: Environment Management

The system MUST support creating and managing environments with unique API keys, each environment belonging to exactly one project, with key uniqueness scoped to `(project, key)` rather than global.

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

### Requirement: Feature Flag Management

The system MUST support creating and managing feature flags within environments.

#### Scenario: Create feature flag

- GIVEN an environment exists
- WHEN POST /api/v1/flags/ with environment_id, key, name
- THEN system creates flag with UUID, is_enabled=False, flag_type=BOOLEAN
- AND flag is unique per (environment, key)

#### Scenario: Toggle feature flag

- GIVEN a feature flag exists with is_enabled=False
- WHEN PATCH /api/v1/flags/{id}/ with is_enabled=True
- THEN system updates flag and publishes event to Redis Streams
- AND event contains full flag payload

#### Scenario: Flag type validation

- GIVEN a feature flag creation request
- WHEN flag_type is not BOOLEAN or MULTIVARIATE
- THEN system returns 400 error with valid flag types

### Requirement: Strategy Rule Management

The system MUST support creating and managing strategy rules for feature flags.

#### Scenario: Create strategy rule

- GIVEN a feature flag exists
- WHEN POST /api/v1/rules/ with flag_id, priority, operator_logic
- THEN system creates rule with UUID and default priority=0
- AND rule is linked to the specified flag

#### Scenario: Rule priority ordering

- GIVEN a flag with rules at priorities 0, 1, 2
- WHEN evaluating the flag
- THEN rules are evaluated in priority order (0 first)

#### Scenario: Operator logic validation

- GIVEN a strategy rule creation request
- WHEN operator_logic is not AND or OR
- THEN system returns 400 error with valid operator types

### Requirement: Condition Management

The system MUST support creating and managing conditions for strategy rules.

#### Scenario: Create condition

- GIVEN a strategy rule exists
- WHEN POST /api/v1/conditions/ with rule_id, attribute, operator, value
- THEN system creates condition with UUID
- AND condition is linked to the specified rule

#### Scenario: Condition operator validation

- GIVEN a condition creation request
- WHEN operator is not in allowed list (EQUALS, NOT_EQUALS, GREATER_THAN, LESS_THAN, IN_LIST, CONTAINS)
- THEN system returns 400 error with valid operators

#### Scenario: Condition value as JSON

- GIVEN a condition with attribute="plan_type"
- WHEN value is {"type": "string", "value": "premium"}
- THEN system stores value as JSONField
- AND value can be queried later for evaluation

### Requirement: Cascade Deletion

The system MUST cascade deletes from parent to child entities.

#### Scenario: Delete environment cascades

- GIVEN an environment with flags, rules, and conditions
- WHEN DELETE /api/v1/environments/{id}/
- THEN all associated flags, rules, and conditions are deleted
- AND Redis Streams event is published for each deleted flag

#### Scenario: Delete flag cascades

- GIVEN a feature flag with rules and conditions
- WHEN DELETE /api/v1/flags/{id}/
- THEN all associated rules and conditions are deleted
- AND Redis Streams event is published for flag deletion

### Requirement: Tenant-Scoped Flag CRUD

The system MUST scope reads of `FeatureFlag`, `StrategyRule`, `Condition`, and `FlagOverride` to environments the requesting user can view, and MUST reject any write whose parent-object reference (environment, flag, or rule) resolves outside the capability-scoped set for that write.

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

### Requirement: UUID Primary Keys

The system MUST use UUIDs as primary keys for all models.

#### Scenario: UUID generation

- GIVEN any model creation request
- WHEN system creates the record
- THEN id field is a valid UUID v4
- AND id is automatically generated, not user-provided

## Key Learnings

1. Flag management specs define CRUD operations with proper validation and cascade behavior.
2. UUID primary keys are used throughout for distributed-friendly identification.
3. Redis Streams events are published on flag changes for real-time SSE updates.
4. Cascade deletion ensures data consistency when parent entities are removed.