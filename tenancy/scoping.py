"""
Join-free queryset scoping (design D4).

Every branch of every `OR` here is a scalar subquery (`pk__in=<queryset>` or
`field__in=<queryset>.values(...)`) filtering the model's own column. No
membership table is ever traversed as a JOIN in the outer query, so nothing
fans out and `.distinct()` is needed nowhere. The invariant is asserted
structurally by `tests.conftest.assert_membership_never_joined`, not by
grepping for `.distinct(`.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from core_flags.models import Environment
from tenancy.capabilities import (
    ENV_ROLES_GRANTING,
    ORG_ROLES_GRANTING,
    PROJECT_ROLES_GRANTING,
    Capability,
    resolve_capabilities,
    validate_capability,
)
from tenancy.models import (
    EnvironmentMembership,
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
)

User = get_user_model()


def orgs_with(user: User, capability: str) -> QuerySet[Organization]:
    """Organizations where `user` holds `capability`, via one scalar subquery."""
    validate_capability(capability)
    return Organization.objects.filter(
        pk__in=OrganizationMembership.objects.filter(
            user=user, role__in=ORG_ROLES_GRANTING[capability]
        ).values("organization_id")
    )


def projects_with(user: User, capability: str) -> QuerySet[Project]:
    """Projects where `user` holds `capability`, cascading from org role too."""
    validate_capability(capability)
    # Layer 2's own enforcement (defence-in-depth alongside the removal
    # cascade in tenancy.models): a standalone ProjectMembership/
    # EnvironmentMembership row only counts when the user still belongs to
    # that project's organization at all -- any role. Without this, an
    # orphan (left behind by a bug, a direct database edit, or a future
    # migration -- not just a removal this app forgot to cascade) would
    # silently keep granting access. `user_org_ids` is a scalar subquery
    # over OrganizationMembership's own columns; joining it against Project
    # happens inside the ProjectMembership subquery below, never in the
    # outer Project query's own alias_map, so the no-join invariant survives.
    user_org_ids = OrganizationMembership.objects.filter(user=user).values("organization_id")
    predicate = Q(organization__in=orgs_with(user, capability).values("pk")) | Q(
        pk__in=ProjectMembership.objects.filter(
            user=user,
            role__in=PROJECT_ROLES_GRANTING[capability],
            project__organization__in=user_org_ids,
        ).values("project_id")
    )
    if capability == Capability.PROJECT_VIEW:
        # D4's documented asymmetry: any EnvironmentMembership at all — no
        # matter its role, and with no ProjectMembership required — implies
        # visibility of that environment's parent project (mirrors
        # resolve_capabilities' narrow implication). Still a scalar subquery
        # on Project's own pk, so the no-join invariant survives it. No other
        # capability takes this branch: an environment grant implies nothing
        # else at the project level. Same organization-membership prerequisite
        # as above -- an orphaned EnvironmentMembership implies nothing either.
        predicate |= Q(
            pk__in=Environment.objects.filter(
                pk__in=EnvironmentMembership.objects.filter(
                    user=user, environment__project__organization__in=user_org_ids
                ).values("environment_id")
            ).values("project_id")
        )
    return Project.objects.filter(predicate)


def environments_with(user: User, capability: str) -> QuerySet[Environment]:
    """Environments where `user` holds `capability`, cascading from org/project role too."""
    validate_capability(capability)
    # See projects_with: the same organization-membership prerequisite for a
    # standalone EnvironmentMembership row.
    user_org_ids = OrganizationMembership.objects.filter(user=user).values("organization_id")
    return Environment.objects.filter(
        Q(project__in=projects_with(user, capability).values("pk"))
        | Q(
            pk__in=EnvironmentMembership.objects.filter(
                user=user,
                role__in=ENV_ROLES_GRANTING[capability],
                environment__project__organization__in=user_org_ids,
            ).values("environment_id")
        )
    )


def capabilities_for(user: User, environment: Environment) -> frozenset[str]:
    """
    Per-object effective capabilities on one environment: 3 membership
    lookups plus `environment.project` (design D3/D5). Callers on a hot path
    should `select_related("environment__project")` beforehand.
    """
    org_role = (
        OrganizationMembership.objects.filter(
            organization=environment.project.organization, user=user
        )
        .values_list("role", flat=True)
        .first()
    )
    project_role = (
        ProjectMembership.objects.filter(project=environment.project, user=user)
        .values_list("role", flat=True)
        .first()
    )
    env_role = (
        EnvironmentMembership.objects.filter(environment=environment, user=user)
        .values_list("role", flat=True)
        .first()
    )
    return resolve_capabilities(org_role, project_role, env_role)
