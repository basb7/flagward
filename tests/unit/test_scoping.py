"""
Tests for join-free queryset scoping (design D4; spec/tenancy-model: Union
Role Resolution consistency; spec/access-control: the enforcement layers rest
on these helpers).

Every helper must resolve to the exact same answer as `resolve_capabilities`
(the consistency invariant), must never join a membership table (the
no-fan-out invariant), and must reject an unknown capability string loudly.
"""
import itertools

import pytest

from tenancy.capabilities import ALL_CAPABILITIES, Capability, resolve_capabilities
from tenancy.models import EnvironmentRole, OrganizationRole, ProjectRole
from tenancy.scoping import environments_with, orgs_with, projects_with

_ORG_ROLES = (None, OrganizationRole.ADMIN, OrganizationRole.VIEWER)
_PROJECT_ROLES = (None, ProjectRole.ADMIN, ProjectRole.EDITOR, ProjectRole.OPERATOR, ProjectRole.VIEWER)
_ENV_ROLES = (None, EnvironmentRole.ADMIN, EnvironmentRole.EDITOR, EnvironmentRole.OPERATOR, EnvironmentRole.VIEWER)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "org_role,project_role,env_role",
    list(itertools.product(_ORG_ROLES, _PROJECT_ROLES, _ENV_ROLES)),
)
def test_environments_with_matches_resolve_capabilities(
    org_role, project_role, env_role, organization, project, environment, user, grant
):
    """
    design D7 test 4 — the consistency invariant:

        c in resolve_capabilities(org_role, project_role, env_role)
            <=>  E in environments_with(u, c)

    for every environment E and every capability c. This is what makes the
    frontend's grant preview (which only calls resolve_capabilities) provably
    identical to what enforcement (which calls environments_with) actually
    allows.
    """
    if org_role is not None:
        grant(user, org=organization, role=org_role)
    if project_role is not None:
        grant(user, project=project, role=project_role)
    if env_role is not None:
        grant(user, environment=environment, role=env_role)

    expected = resolve_capabilities(org_role, project_role, env_role)

    for capability in ALL_CAPABILITIES:
        is_visible = environments_with(user, capability).filter(pk=environment.pk).exists()
        assert is_visible == (capability in expected), (
            f"capability={capability} org={org_role} project={project_role} env={env_role}"
        )


@pytest.mark.django_db
@pytest.mark.parametrize("capability", sorted(ALL_CAPABILITIES))
def test_no_membership_join(capability, user, assert_membership_never_joined):
    """
    design D7 test 5 — the structural no-join guard, over the three scoping
    helpers x every capability in the catalogue.
    """
    assert_membership_never_joined(orgs_with(user, capability))
    assert_membership_never_joined(projects_with(user, capability))
    assert_membership_never_joined(environments_with(user, capability))


@pytest.mark.django_db
def test_no_fan_out(organization, project, environment, user, grant):
    """
    design D7 test 6 — the behavioural no-fan-out guard: one user holding an
    org membership, a project membership, and an environment membership that
    all grant the same capability on the same environment must still count
    that environment exactly once. A join-based implementation would fan out
    to 3 rows.
    """
    grant(user, org=organization, role=OrganizationRole.ADMIN)
    grant(user, project=project, role=ProjectRole.ADMIN)
    grant(user, environment=environment, role=EnvironmentRole.ADMIN)

    assert environments_with(user, Capability.ENVIRONMENT_VIEW).count() == 1


@pytest.mark.django_db
def test_unknown_capability_raises_on_all_three_helpers(user):
    """spec/design D3: a typo in a capability string fails loudly, not silently."""
    with pytest.raises(ValueError):
        orgs_with(user, "org.launch_the_missiles")
    with pytest.raises(ValueError):
        projects_with(user, "org.launch_the_missiles")
    with pytest.raises(ValueError):
        environments_with(user, "org.launch_the_missiles")


@pytest.mark.django_db
def test_project_view_narrow_special_case(project, environment, user, grant):
    """
    design D4's documented asymmetry: an EnvironmentMembership alone (no
    ProjectMembership) still makes the parent project visible under
    `project.view` — this is the one branch `projects_with` special-cases.
    """
    grant(user, environment=environment, role=EnvironmentRole.VIEWER)

    assert projects_with(user, Capability.PROJECT_VIEW).filter(pk=project.pk).exists()
    # And it grants nothing else at the project level.
    assert not projects_with(user, Capability.PROJECT_MANAGE).filter(pk=project.pk).exists()
