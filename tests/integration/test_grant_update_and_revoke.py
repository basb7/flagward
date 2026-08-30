"""
Tests for PATCH/DELETE on `/api/v1/tenancy/project-memberships/{id}/` and
`/api/v1/tenancy/environment-memberships/{id}/`.

`ProjectMembershipViewSet` and `EnvironmentMembershipViewSet` shipped with
only `ListModelMixin`/`CreateModelMixin` (tasks 6.6/6.7): a role could be
granted but never changed or revoked, and because `create` was the only
write path, a second grant attempt collided with
`UniqueConstraint(fields=["project", "user"])` (or the environment
equivalent) and surfaced Django's table-level "must make a unique set"
message instead of updating the existing row.

Both mutations must enforce the same `project.manage_members` gate and the
same tenant scoping the create path already uses (`OrganizationMembershipViewSet`
is the pattern: a scoped `get_queryset` plus a `_require_manage_permission`
check inside the mutation).
"""
import pytest
from django.contrib.auth import get_user_model

from tenancy.models import (
    EnvironmentMembership,
    EnvironmentRole,
    OrganizationRole,
    ProjectMembership,
    ProjectRole,
)

User = get_user_model()


@pytest.mark.django_db
class TestProjectMembershipUpdate:
    """PATCH /api/v1/tenancy/project-memberships/{id}/."""

    def test_project_admin_changes_a_role(self, api_client, user, grant, organization, project):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/project-memberships/{membership.id}/",
            {"role": ProjectRole.EDITOR},
            format="json",
        )

        assert response.status_code == 200
        membership.refresh_from_db()
        assert membership.role == ProjectRole.EDITOR

    def test_re_granting_a_role_is_not_the_way_to_change_it(
        self, api_client, user, grant, organization, project
    ):
        """
        The unique-constraint collision the bug report describes: re-POSTing
        an existing (project, user) pair must still fail -- the fix is a PATCH
        endpoint, not a change in create's behaviour.
        """
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        grant(target, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/project-memberships/",
            {"project": str(project.id), "user": target.id, "role": ProjectRole.EDITOR},
            format="json",
        )

        assert response.status_code == 400
        assert "non_field_errors" in response.data

    def test_update_rejected_without_manage_members_capability(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.VIEWER)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/project-memberships/{membership.id}/",
            {"role": ProjectRole.EDITOR},
            format="json",
        )

        assert response.status_code == 403
        membership.refresh_from_db()
        assert membership.role == ProjectRole.VIEWER

    def test_update_rejected_across_tenants(self, api_client, user, grant, make_project):
        """A grant in a project the caller cannot administer must not be reachable."""
        foreign_project = make_project(name="Foreign", key="foreign")
        foreign_org = foreign_project.organization
        foreign_admin = User.objects.create_user(username="foreign-admin", password="tram-quartz-19-belt")
        grant(foreign_admin, org=foreign_org, role=OrganizationRole.ADMIN)
        membership = ProjectMembership.objects.create(
            project=foreign_project, user=foreign_admin, role=ProjectRole.VIEWER
        )
        client = api_client(user)  # `user` has no membership anywhere in foreign_org

        response = client.patch(
            f"/api/v1/tenancy/project-memberships/{membership.id}/",
            {"role": ProjectRole.EDITOR},
            format="json",
        )

        assert response.status_code == 404
        membership.refresh_from_db()
        assert membership.role == ProjectRole.VIEWER

    def test_project_admin_revokes_a_grant(self, api_client, user, grant, organization, project):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/project-memberships/{membership.id}/")

        assert response.status_code == 204
        assert not ProjectMembership.objects.filter(id=membership.id).exists()

    def test_destroy_rejected_without_manage_members_capability(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.VIEWER)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/project-memberships/{membership.id}/")

        assert response.status_code == 403
        assert ProjectMembership.objects.filter(id=membership.id).exists()

    def test_destroy_rejected_across_tenants(self, api_client, user, grant, make_project):
        foreign_project = make_project(name="Foreign", key="foreign")
        foreign_org = foreign_project.organization
        foreign_admin = User.objects.create_user(username="foreign-admin", password="tram-quartz-19-belt")
        grant(foreign_admin, org=foreign_org, role=OrganizationRole.ADMIN)
        membership = ProjectMembership.objects.create(
            project=foreign_project, user=foreign_admin, role=ProjectRole.VIEWER
        )
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/project-memberships/{membership.id}/")

        assert response.status_code == 404
        assert ProjectMembership.objects.filter(id=membership.id).exists()


@pytest.mark.django_db
class TestEnvironmentMembershipUpdate:
    """PATCH /api/v1/tenancy/environment-memberships/{id}/."""

    def test_project_admin_changes_a_role(
        self, api_client, user, grant, organization, project, environment
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, environment=environment, role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/environment-memberships/{membership.id}/",
            {"role": EnvironmentRole.OPERATOR},
            format="json",
        )

        assert response.status_code == 200
        membership.refresh_from_db()
        assert membership.role == EnvironmentRole.OPERATOR

    def test_update_rejected_without_manage_members_capability(
        self, api_client, user, grant, organization, project, environment
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.VIEWER)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, environment=environment, role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/environment-memberships/{membership.id}/",
            {"role": EnvironmentRole.OPERATOR},
            format="json",
        )

        assert response.status_code == 403
        membership.refresh_from_db()
        assert membership.role == EnvironmentRole.VIEWER

    def test_update_rejected_across_tenants(
        self, api_client, user, grant, make_project, make_environment
    ):
        foreign_project = make_project(name="Foreign", key="foreign")
        foreign_org = foreign_project.organization
        foreign_environment = make_environment(project=foreign_project, key="stage", name="Staging")
        foreign_admin = User.objects.create_user(username="foreign-admin", password="tram-quartz-19-belt")
        grant(foreign_admin, org=foreign_org, role=OrganizationRole.ADMIN)
        membership = EnvironmentMembership.objects.create(
            environment=foreign_environment, user=foreign_admin, role=EnvironmentRole.VIEWER
        )
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/environment-memberships/{membership.id}/",
            {"role": EnvironmentRole.OPERATOR},
            format="json",
        )

        assert response.status_code == 404
        membership.refresh_from_db()
        assert membership.role == EnvironmentRole.VIEWER

    def test_project_admin_revokes_a_grant(
        self, api_client, user, grant, organization, project, environment
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, environment=environment, role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/environment-memberships/{membership.id}/")

        assert response.status_code == 204
        assert not EnvironmentMembership.objects.filter(id=membership.id).exists()

    def test_destroy_rejected_without_manage_members_capability(
        self, api_client, user, grant, organization, project, environment
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.VIEWER)
        target = User.objects.create_user(username="target", password="tram-quartz-19-belt")
        grant(target, org=organization, role=OrganizationRole.USER)
        membership = grant(target, environment=environment, role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/environment-memberships/{membership.id}/")

        assert response.status_code == 403
        assert EnvironmentMembership.objects.filter(id=membership.id).exists()

    def test_destroy_rejected_across_tenants(
        self, api_client, user, grant, make_project, make_environment
    ):
        foreign_project = make_project(name="Foreign", key="foreign")
        foreign_org = foreign_project.organization
        foreign_environment = make_environment(project=foreign_project, key="stage", name="Staging")
        foreign_admin = User.objects.create_user(username="foreign-admin", password="tram-quartz-19-belt")
        grant(foreign_admin, org=foreign_org, role=OrganizationRole.ADMIN)
        membership = EnvironmentMembership.objects.create(
            environment=foreign_environment, user=foreign_admin, role=EnvironmentRole.VIEWER
        )
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/environment-memberships/{membership.id}/")

        assert response.status_code == 404
        assert EnvironmentMembership.objects.filter(id=membership.id).exists()
