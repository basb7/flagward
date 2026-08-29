"""
Tests for POST /api/v1/tenancy/project-memberships/ and
POST /api/v1/tenancy/environment-memberships/ (spec/organization-management:
Per-Project and Per-Environment Role Grants).
"""
import pytest
from django.contrib.auth import get_user_model

from tenancy.models import (
    EnvironmentMembership,
    OrganizationRole,
    ProjectMembership,
    ProjectRole,
)

User = get_user_model()


@pytest.mark.django_db
class TestRoleGrants:
    """spec: Per-Project and Per-Environment Role Grants (task 6.6/6.7)."""

    def test_grant_project_role(self, api_client, user, grant, organization, project):
        """A project admin grants an EDITOR role on a project to a fellow org member."""
        grant(user, project=project, role=ProjectRole.ADMIN)
        target = User.objects.create_user(username="target", password="secret")
        grant(target, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/project-memberships/",
            {"project": str(project.id), "user": target.id, "role": ProjectRole.EDITOR},
            format="json",
        )

        assert response.status_code == 201
        assert ProjectMembership.objects.filter(
            project=project, user=target, role=ProjectRole.EDITOR
        ).exists()

    def test_grant_environment_role(self, api_client, user, grant, organization, project, environment):
        """A project admin grants an OPERATOR role on an environment to a fellow org member."""
        grant(user, project=project, role=ProjectRole.ADMIN)
        target = User.objects.create_user(username="target", password="secret")
        grant(target, org=organization, role=OrganizationRole.USER)
        grant(target, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/environment-memberships/",
            {"environment": str(environment.id), "user": target.id, "role": "OPERATOR"},
            format="json",
        )

        assert response.status_code == 201
        assert EnvironmentMembership.objects.filter(
            environment=environment, user=target, role="OPERATOR"
        ).exists()

    def test_grant_rejected_without_org_membership(self, api_client, user, project):
        """
        Granting a project or environment role to a user with no
        OrganizationMembership in the owning organization must be rejected.
        """
        grant_admin = User.objects.create_user(username="admin", password="secret")
        ProjectMembership.objects.create(project=project, user=grant_admin, role=ProjectRole.ADMIN)
        stranger = User.objects.create_user(username="stranger", password="secret")
        client = api_client(grant_admin)

        response = client.post(
            "/api/v1/tenancy/project-memberships/",
            {"project": str(project.id), "user": stranger.id, "role": ProjectRole.EDITOR},
            format="json",
        )

        assert response.status_code == 400
        assert not ProjectMembership.objects.filter(project=project, user=stranger).exists()

    def test_grant_rejected_without_manage_members_capability(self, api_client, user, grant, organization, project):
        """
        A user with no `project.manage_members` capability cannot grant a
        role: the `project` field narrows to `.none()` for them (design D5,
        Layer 2), so the chosen project is an invalid choice, not a
        readable-but-forbidden one.
        """
        grant(user, project=project, role=ProjectRole.VIEWER)
        target = User.objects.create_user(username="target", password="secret")
        grant(target, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/project-memberships/",
            {"project": str(project.id), "user": target.id, "role": ProjectRole.EDITOR},
            format="json",
        )

        assert response.status_code == 400
        assert not ProjectMembership.objects.filter(project=project, user=target).exists()
