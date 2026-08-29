"""
Tests for the pure capability resolver (design D3; spec/tenancy-model:
Capability Catalogue by Level, Role to Capability Grants, Union Role
Resolution, The Carve-Out Trap).

`resolve_capabilities` touches no database, no request, and no user object.
"""
import itertools

import pytest

from tenancy.capabilities import (
    ALL_CAPABILITIES,
    ENV_ROLE_CAPS,
    ORG_ROLE_CAPS,
    PROJECT_ROLE_CAPS,
    Capability,
    resolve_capabilities,
)
from tenancy.models import EnvironmentRole, OrganizationRole, ProjectRole

# Ground truth authored independently of tenancy.capabilities' own tables, so
# this test catches drift in the production role -> capability grants, not
# just a bug in the union algebra that combines them.
_ORG_ADMIN = frozenset(ALL_CAPABILITIES)  # org ADMIN dominates every level; see spec below.
_ORG_CAPS = {
    None: frozenset(),
    OrganizationRole.ADMIN: _ORG_ADMIN,
    OrganizationRole.USER: frozenset({Capability.ORG_VIEW}),
}

_PROJECT_VIEWER = frozenset(
    {Capability.PROJECT_VIEW, Capability.ENVIRONMENT_VIEW, Capability.ANALYTICS_VIEW}
)
_PROJECT_OPERATOR = _PROJECT_VIEWER | {Capability.OVERRIDE_MANAGE}
_PROJECT_EDITOR = _PROJECT_OPERATOR | {Capability.FLAG_EDIT}
_PROJECT_ADMIN = _PROJECT_EDITOR | {
    Capability.PROJECT_MANAGE,
    Capability.PROJECT_MANAGE_MEMBERS,
    Capability.PROJECT_DELETE,
    Capability.ENVIRONMENT_CREATE,
    Capability.ENVIRONMENT_DELETE,
    Capability.ENVIRONMENT_MANAGE,
}
_PROJECT_CAPS = {
    None: frozenset(),
    ProjectRole.ADMIN: _PROJECT_ADMIN,
    ProjectRole.EDITOR: _PROJECT_EDITOR,
    ProjectRole.OPERATOR: _PROJECT_OPERATOR,
    ProjectRole.VIEWER: _PROJECT_VIEWER,
}

_ENV_VIEWER = frozenset({Capability.ENVIRONMENT_VIEW, Capability.ANALYTICS_VIEW})
_ENV_OPERATOR = _ENV_VIEWER | {Capability.OVERRIDE_MANAGE}
_ENV_EDITOR = _ENV_OPERATOR | {Capability.FLAG_EDIT}
_ENV_ADMIN = _ENV_EDITOR | {Capability.ENVIRONMENT_MANAGE}
_ENV_CAPS = {
    None: frozenset(),
    EnvironmentRole.ADMIN: _ENV_ADMIN,
    EnvironmentRole.EDITOR: _ENV_EDITOR,
    EnvironmentRole.OPERATOR: _ENV_OPERATOR,
    EnvironmentRole.VIEWER: _ENV_VIEWER,
}

_ORG_ROLES = (None, OrganizationRole.ADMIN, OrganizationRole.USER)
_PROJECT_ROLES = (None, ProjectRole.ADMIN, ProjectRole.EDITOR, ProjectRole.OPERATOR, ProjectRole.VIEWER)
_ENV_ROLES = (None, EnvironmentRole.ADMIN, EnvironmentRole.EDITOR, EnvironmentRole.OPERATOR, EnvironmentRole.VIEWER)


def _expected(org_role, project_role, env_role):
    caps = _ORG_CAPS[org_role] | _PROJECT_CAPS[project_role] | _ENV_CAPS[env_role]
    if env_role is not None:
        # Narrow implication (spec: "Environment membership implies parent
        # project visibility only"): any environment grant makes the parent
        # project navigable and nothing else about it.
        caps = caps | {Capability.PROJECT_VIEW}
    return caps


@pytest.mark.parametrize(
    "org_role,project_role,env_role",
    list(itertools.product(_ORG_ROLES, _PROJECT_ROLES, _ENV_ROLES)),
)
def test_resolve_capabilities_matrix(org_role, project_role, env_role):
    """design D7 test 1: 4 org x 5 project x 5 env roles, full capability set asserted each time."""
    expected = _expected(org_role, project_role, env_role)
    actual = resolve_capabilities(org_role, project_role, env_role)

    # Full-catalogue assertion: check every capability's membership individually
    # (not just `actual == expected`) so a resolver that leaks one unexpected
    # capability, alongside otherwise-correct results, is still caught.
    for capability in ALL_CAPABILITIES:
        assert (capability in actual) == (capability in expected), (
            f"capability={capability} org={org_role} project={project_role} env={env_role}"
        )


def test_union_org_admin_not_narrowed():
    """design D7 test 2 / spec: Organization ADMIN cannot be narrowed by a lower grant."""
    caps = resolve_capabilities(OrganizationRole.ADMIN, ProjectRole.VIEWER, None)

    assert Capability.FLAG_EDIT in caps


def test_narrow_implication_project_view_only():
    """design D7 test 3 / spec: Environment membership implies parent project visibility only."""
    caps = resolve_capabilities(None, None, EnvironmentRole.VIEWER)

    project_level_capabilities = frozenset(
        {
            Capability.PROJECT_VIEW,
            Capability.PROJECT_MANAGE,
            Capability.PROJECT_MANAGE_MEMBERS,
            Capability.PROJECT_DELETE,
            Capability.ENVIRONMENT_CREATE,
            Capability.ENVIRONMENT_DELETE,
        }
    )
    assert caps & project_level_capabilities == frozenset({Capability.PROJECT_VIEW})


def test_no_membership_at_a_level_grants_nothing_extra():
    """spec: No membership at a level grants nothing extra."""
    caps = resolve_capabilities(OrganizationRole.USER, None, None)

    assert caps == frozenset({Capability.ORG_VIEW})


def test_grants_at_different_levels_combine():
    """spec: Grants at different levels combine."""
    caps = resolve_capabilities(None, ProjectRole.VIEWER, EnvironmentRole.EDITOR)

    assert Capability.PROJECT_VIEW in caps
    assert Capability.FLAG_EDIT in caps
    assert Capability.OVERRIDE_MANAGE in caps


def test_wide_grant_plus_attempted_carve_out_does_not_work():
    """spec: Wide grant plus attempted carve-out does not work (union only adds)."""
    caps = resolve_capabilities(None, ProjectRole.EDITOR, EnvironmentRole.VIEWER)

    assert Capability.FLAG_EDIT in caps


def test_unknown_capability_raises_value_error():
    from tenancy.capabilities import validate_capability

    with pytest.raises(ValueError):
        validate_capability("flag.launch_the_missiles")


def test_max_seats_boundary():
    from tenancy.capabilities import max_seats
    from tenancy.models import Plan

    assert max_seats(Plan.COMMUNITY) is None
    assert max_seats(Plan.STARTER) == 5
    assert max_seats(Plan.TEAM) == 25


def test_no_two_roles_at_one_level_are_interchangeable():
    """
    Two roles granting identical capabilities are one role wearing two names.

    The distinction survives in the enum, in the database's CheckConstraint and
    in whatever UI assigns it, while meaning nothing — so it can only mislead
    the person choosing between them. It also hides intent: nobody can tell
    whether the roles were meant to differ and the difference was lost, or
    whether one was redundant from the start.
    """
    levels = {
        "organization": (OrganizationRole, ORG_ROLE_CAPS),
        "project": (ProjectRole, PROJECT_ROLE_CAPS),
        "environment": (EnvironmentRole, ENV_ROLE_CAPS),
    }

    for level, (role_enum, grants) in levels.items():
        pairs = itertools.combinations(role_enum.values, 2)
        for role_a, role_b in pairs:
            assert grants[role_a] != grants[role_b], (
                f"{level} roles {role_a} and {role_b} grant identical capabilities"
            )


def test_organization_roster_is_admin_and_user():
    """
    The organization level has exactly two roles, matching Flagsmith's
    organisation model: an administrator with full access, and a plain member
    whose reach comes entirely from project and environment grants below.

    The plain role is USER rather than VIEWER on purpose. VIEWER reads as
    "can view things", which at the organization level would suggest access
    to what the organization contains. It grants only ORG_VIEW -- enough to
    know which organization you belong to and navigate into it -- and nothing
    about the projects inside, which arrive one level down or not at all.
    """
    assert set(OrganizationRole.values) == {"ADMIN", "USER"}
