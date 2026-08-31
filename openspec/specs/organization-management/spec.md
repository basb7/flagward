# Organization Management Specification

## Purpose

Registration bootstrap, invitation-based membership, per-project and
per-environment role grants, and seat accounting against the plan.

## Requirements

### Requirement: Self-Registration Creates Only the User

Registration MUST remain open. Registering a new user MUST create exactly
that `auth.User` and MUST NOT create an `Organization` or any
`OrganizationMembership`. The first organization is created explicitly from
the dashboard's empty state, which is what lets the person name it
themselves instead of inheriting a generated name.

#### Scenario: New registration creates a user and no organization

- GIVEN no account exists for a given email
- WHEN the user completes registration
- THEN exactly one `auth.User` is created
- AND no `Organization` is created
- AND no `OrganizationMembership` is created

### Requirement: An Invitation Link Is the Only Way Into an Organization

A member holding `org.manage_members` MUST be able to issue a single-use,
expiring invitation link scoped to one organization and one organization
role, and MUST be able to revoke it before it is accepted. There is no
endpoint through which one member sets another member's password -- an
invitation is accepted by the invited person themselves, who chooses their
own password (or already has an account and simply logs in). Accepting a
still-valid invitation MUST create exactly one `OrganizationMembership` for
the accepting user with the invitation's role, and consumes one seat at that
moment, not before.

#### Scenario: Admin invites and the recipient accepts

- GIVEN an organization below its seat limit
- WHEN an `ADMIN` issues an invitation with organization role `USER` and the recipient accepts it
- THEN a new `OrganizationMembership` is created for the accepting user with role `USER`

#### Scenario: Non-privileged member cannot issue an invitation

- GIVEN a user holds organization role `USER`
- WHEN that user attempts to issue an invitation
- THEN the system rejects the request

#### Scenario: A revoked or expired invitation cannot be accepted

- GIVEN an invitation that has been revoked, or whose expiry has passed
- WHEN someone attempts to accept it
- THEN the system rejects the request
- AND no `OrganizationMembership` is created

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
organization's own `ADMIN`. `COMMUNITY` plan has unlimited seats. Any other plan MUST reject the
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
