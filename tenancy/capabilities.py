"""
The frozen capability catalogue and the pure union-resolution logic
(design D3; spec/tenancy-model: Capability Catalogue by Level, Role to
Capability Grants, Union Role Resolution).

`resolve_capabilities` touches no database, no request, and no user object.
Everything else in the access-control model — per-object permission checks
(`tenancy.permissions`), set-valued queryset scoping (`tenancy.scoping`), and
the frontend's grant preview — is derived from this one function and proven
equal to it by test, so drift between "what the UI shows" and "what is
actually enforced" is structurally impossible.
"""
from __future__ import annotations

from tenancy.models import EnvironmentRole, OrganizationRole, Plan, ProjectRole


class Capability:
    """
    String constants for every capability in the catalogue
    (spec: Capability Catalogue by Level).
    """

    # Organization level
    ORG_VIEW = "org.view"
    ORG_MANAGE_MEMBERS = "org.manage_members"
    ORG_MANAGE = "org.manage"
    ORG_DELETE = "org.delete"
    PROJECT_CREATE = "project.create"

    # Project level
    PROJECT_VIEW = "project.view"
    PROJECT_MANAGE = "project.manage"
    PROJECT_MANAGE_MEMBERS = "project.manage_members"
    PROJECT_DELETE = "project.delete"
    ENVIRONMENT_CREATE = "environment.create"
    ENVIRONMENT_DELETE = "environment.delete"

    # Environment level
    ENVIRONMENT_VIEW = "environment.view"
    ENVIRONMENT_MANAGE = "environment.manage"
    FLAG_EDIT = "flag.edit"
    OVERRIDE_MANAGE = "override.manage"
    ANALYTICS_VIEW = "analytics.view"


ALL_CAPABILITIES: frozenset[str] = frozenset(
    value for name, value in vars(Capability).items() if not name.startswith("_")
)

EMPTY: frozenset[str] = frozenset()

# --- Role -> capability grants, one dict per level (spec: Role to Capability Grants) ---
#
# Each level's roster is cumulative (ADMIN ⊇ EDITOR ⊇ OPERATOR ⊇ VIEWER where
# a level has that many roles), matching the spec's "Grants at different
# levels combine" and "Wide grant plus attempted carve-out does not work"
# scenarios: a project- or environment-level EDITOR/OPERATOR grant cascades
# the corresponding environment-scoped capability across everything it owns.

# Organization ADMIN dominates every lower level: spec "Organization ADMIN
# cannot be narrowed by a lower grant" requires that adding every possible
# lower-level VIEWER row leaves an org ADMIN's resolved capabilities
# unchanged, which only holds if ADMIN already grants the full catalogue.
#
# That makes ADMIN a full key to the account rather than a day-to-day
# administration role — it holds ORG_DELETE, and the hierarchy cascades. This
# matches Flagsmith, whose organisation administrator likewise "has full
# access to everything", and it is why the members UI must warn on assignment.
# The members screen mirrors this: it never badges an organization ADMIN as
# lacking access, because an ADMIN needs no grant rows to hold everything.
# That is a policy duplicated in TypeScript, so if this line ever stops
# meaning "an ADMIN holds the whole catalogue", update
# frontend/src/app/dashboard/members/page.tsx with it. The matrix test in
# tests/unit/test_capabilities.py fails loudly on the change; this note is
# what tells you the other place to look.
_ORG_ADMIN_CAPS: frozenset[str] = ALL_CAPABILITIES

ORG_ROLE_CAPS: dict[str, frozenset[str]] = {
    OrganizationRole.ADMIN: _ORG_ADMIN_CAPS,
    OrganizationRole.USER: frozenset({Capability.ORG_VIEW}),
}

_PROJECT_VIEWER_CAPS = frozenset(
    {Capability.PROJECT_VIEW, Capability.ENVIRONMENT_VIEW, Capability.ANALYTICS_VIEW}
)
_PROJECT_OPERATOR_CAPS = _PROJECT_VIEWER_CAPS | {Capability.OVERRIDE_MANAGE}
_PROJECT_EDITOR_CAPS = _PROJECT_OPERATOR_CAPS | {Capability.FLAG_EDIT}
_PROJECT_ADMIN_CAPS = _PROJECT_EDITOR_CAPS | {
    Capability.PROJECT_MANAGE,
    Capability.PROJECT_MANAGE_MEMBERS,
    Capability.PROJECT_DELETE,
    Capability.ENVIRONMENT_CREATE,
    Capability.ENVIRONMENT_DELETE,
    Capability.ENVIRONMENT_MANAGE,
}

PROJECT_ROLE_CAPS: dict[str, frozenset[str]] = {
    ProjectRole.ADMIN: _PROJECT_ADMIN_CAPS,
    ProjectRole.EDITOR: _PROJECT_EDITOR_CAPS,
    ProjectRole.OPERATOR: _PROJECT_OPERATOR_CAPS,
    ProjectRole.VIEWER: _PROJECT_VIEWER_CAPS,
}

_ENV_VIEWER_CAPS = frozenset({Capability.ENVIRONMENT_VIEW, Capability.ANALYTICS_VIEW})
_ENV_OPERATOR_CAPS = _ENV_VIEWER_CAPS | {Capability.OVERRIDE_MANAGE}
_ENV_EDITOR_CAPS = _ENV_OPERATOR_CAPS | {Capability.FLAG_EDIT}
_ENV_ADMIN_CAPS = _ENV_EDITOR_CAPS | {Capability.ENVIRONMENT_MANAGE}

ENV_ROLE_CAPS: dict[str, frozenset[str]] = {
    EnvironmentRole.ADMIN: _ENV_ADMIN_CAPS,
    EnvironmentRole.EDITOR: _ENV_EDITOR_CAPS,
    EnvironmentRole.OPERATOR: _ENV_OPERATOR_CAPS,
    EnvironmentRole.VIEWER: _ENV_VIEWER_CAPS,
}


def validate_capability(capability: str) -> None:
    """
    Raise if `capability` is not one of the frozen catalogue strings.

    A typo in a capability name must fail loudly (`ValueError`), never
    silently resolve to an empty set — an empty set reads as "nobody has
    this", which is an unreportable 403/404 on the read path and a silent
    non-narrowing on the write path (design D3).
    """
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"Unknown capability: {capability!r}")


def resolve_capabilities(
    org_role: str | None,
    project_role: str | None,
    env_role: str | None,
) -> frozenset[str]:
    """
    Union role resolution (spec: Union Role Resolution). A missing membership
    at a level contributes the empty set. No level may reduce a capability
    granted at a higher level — capabilities only ever add (The Carve-Out
    Trap).
    """
    caps = (
        ORG_ROLE_CAPS.get(org_role, EMPTY)
        | PROJECT_ROLE_CAPS.get(project_role, EMPTY)
        | ENV_ROLE_CAPS.get(env_role, EMPTY)
    )
    # Narrow implication (spec: "Environment membership implies parent
    # project visibility only"): any environment grant makes the parent
    # project navigable, and grants nothing else about it.
    if env_role is not None:
        caps = caps | {Capability.PROJECT_VIEW}
    return caps


def _invert(role_caps: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    """Build a capability -> {roles granting it} map from a role -> capabilities map."""
    return {
        capability: frozenset(role for role, caps in role_caps.items() if capability in caps)
        for capability in ALL_CAPABILITIES
    }


# Inverted maps: for a given capability, which roles at that level grant it.
# `.get(capability, EMPTY)` is the correct answer for a *known* capability
# that simply does not exist at that level (e.g. `org.view` asked of
# `ENV_ROLES_GRANTING`) — that is a legitimate empty result, distinct from an
# unknown capability string, which `validate_capability` rejects instead.
ORG_ROLES_GRANTING: dict[str, frozenset[str]] = _invert(ORG_ROLE_CAPS)
PROJECT_ROLES_GRANTING: dict[str, frozenset[str]] = _invert(PROJECT_ROLE_CAPS)
ENV_ROLES_GRANTING: dict[str, frozenset[str]] = _invert(ENV_ROLE_CAPS)


_SEAT_LIMITS: dict[str, int | None] = {
    Plan.COMMUNITY: None,
    Plan.STARTER: 5,
    Plan.TEAM: 25,
}


def max_seats(plan: str) -> int | None:
    """Seat ceiling for a plan. `None` means unlimited."""
    return _SEAT_LIMITS[plan]
