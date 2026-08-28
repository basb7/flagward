# Organization Management Specification

## Purpose

Registration bootstrap, owner/admin-created users, per-project and
per-environment role grants, and seat accounting against the plan.

## Requirements

### Requirement: Self-Registration Auto-Provisions an Organization

Registration MUST remain open. Registering a new user MUST automatically
create exactly one `Organization` with that user as its `OWNER`.

#### Scenario: New registration creates an organization

- GIVEN no account exists for a given email
- WHEN the user completes registration
- THEN exactly one `Organization` is created
- AND the new user holds an `OrganizationMembership` with role `OWNER` in it

### Requirement: Owner/Admin Creates and Attaches Users

A member holding `org.manage_members` MUST be able to create a new user
account and attach it to the organization with an organization role. This
consumes one seat.

#### Scenario: Admin creates a member

- GIVEN an organization below its seat limit
- WHEN an `ADMIN` creates a new user and assigns organization role `VIEWER`
- THEN a new `auth.User` and a new `OrganizationMembership` are created

#### Scenario: Non-privileged member cannot create users

- GIVEN a user holds organization role `VIEWER`
- WHEN that user attempts to create a new organization member
- THEN the system returns 403

### Requirement: Per-Project and Per-Environment Role Grants

A member holding `project.manage_members` MUST be able to grant a
`ProjectMembership` role or an `EnvironmentMembership` role to any user who
already holds an `OrganizationMembership` in the same organization. Granting
either membership for a user without an existing `OrganizationMembership` in
that organization MUST be rejected.

#### Scenario: Grant a project role

- GIVEN a target user already holds an `OrganizationMembership` in Organization X
- WHEN a project admin grants that user role `EDITOR` on Project P (inside Organization X)
- THEN a `ProjectMembership` row is created

#### Scenario: Grant an environment role

- GIVEN a target user already holds a `ProjectMembership` in Project P
- WHEN a project admin grants that user role `OPERATOR` on Environment E (inside Project P)
- THEN an `EnvironmentMembership` row is created

#### Scenario: Grant rejected without an organization membership

- GIVEN a target user holds no `OrganizationMembership` in Organization X
- WHEN a request attempts to grant that user a `ProjectMembership` or `EnvironmentMembership` on an object owned by Organization X
- THEN the system rejects the request

### Requirement: Seat Accounting Against the Plan

One `OrganizationMembership` row equals one consumed seat, including the
`OWNER`. `COMMUNITY` plan has unlimited seats. Any other plan MUST reject the
membership row that would exceed `max_seats(plan)`.

#### Scenario: Under the limit

- GIVEN an organization with `max_seats(plan) = 5` and 4 existing memberships
- WHEN a 5th member is added
- THEN the membership is created

#### Scenario: At the boundary

- GIVEN an organization with `max_seats(plan) = 5` and 5 existing memberships
- WHEN a 6th member is added
- THEN the system returns 400 with error `seat_limit_reached`
- AND no membership row is created

#### Scenario: COMMUNITY plan never blocks

- GIVEN an organization on the `COMMUNITY` plan with 500 existing memberships
- WHEN another member is added
- THEN the membership is created

#### Scenario: Removing a member frees the seat immediately

- GIVEN an organization at its seat limit
- WHEN one `OrganizationMembership` is deleted
- THEN a new member can be added immediately after

#### Scenario: Deactivated user still consumes a seat

- GIVEN a user's `auth.User.is_active` is set to `False`
- WHEN seat count is evaluated
- THEN that user's `OrganizationMembership` still counts toward the limit

#### Scenario: Plan downgraded below current membership count

- GIVEN an organization has 8 members and its plan is downgraded to `max_seats = 5`
- WHEN existing members access the system
- THEN they retain access
- AND adding a 9th member is rejected until the count drops back to 5
