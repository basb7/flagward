"""
Tests for the privilege-retention hole: removing someone from an organization
used to leave their project/environment grants in place, and those grants
kept working (spec/tenancy-model, defence-in-depth follow-up to slice 6b).

Two layers are exercised here:

- Layer 1 (cascade on removal): deleting an `OrganizationMembership` deletes
  that user's `ProjectMembership`/`EnvironmentMembership` rows *within that
  organization*, in one transaction, on every delete path -- the DRF view,
  a direct `instance.delete()`, and Django admin's bulk `queryset.delete()`
  action.
- Layer 2 (an orphan grants nothing): even a grant row that was never
  cascaded away -- created directly through the ORM, bypassing the API's
  organization-membership prerequisite -- must be inert. This is `projects_with`
  and `environments_with` requiring the organization membership at read time,
  independent of Layer 1.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tenancy.models import (
    EnvironmentMembership,
    EnvironmentRole,
    OrganizationMembership,
    OrganizationRole,
    ProjectMembership,
    ProjectRole,
)
from tenancy.scoping import environments_with, projects_with

User = get_user_model()


@pytest.mark.django_db
class TestRemovalRevokesGrantsEndToEnd:
    """The reproduction from the bug report, end to end through the API."""

    def test_removed_member_loses_all_access_and_write(
        self, api_client, user, grant, organization, project, environment, flag
    ):
        admin = User.objects.create_user(username="admin", password="tram-quartz-19-belt")
        grant(admin, org=organization, role=OrganizationRole.ADMIN)
        org_membership = grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.EDITOR)

        pedro_client = api_client(user)

        # Before removal: pedro genuinely has access.
        assert pedro_client.get("/api/v1/tenancy/projects/").data["results"]
        assert pedro_client.get("/api/v1/environments/").data["results"]
        assert pedro_client.get("/api/v1/flags/").data["results"]

        admin_client = api_client(admin)
        response = admin_client.delete(
            f"/api/v1/tenancy/organization-memberships/{org_membership.id}/"
        )
        assert response.status_code == 204

        # After removal: zero projects, zero environments, zero flags visible.
        assert pedro_client.get("/api/v1/tenancy/projects/").data["results"] == []
        assert pedro_client.get("/api/v1/environments/").data["results"] == []
        assert pedro_client.get("/api/v1/flags/").data["results"] == []

        # And no lingering write access either.
        patch_response = pedro_client.patch(
            f"/api/v1/flags/{flag.id}/", {"is_enabled": True}, format="json"
        )
        assert patch_response.status_code in (403, 404)

        assert not ProjectMembership.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestCascadeScopedToOneOrganization:
    """Layer 1: the cascade only touches the organization the removal happened in."""

    def test_removal_leaves_other_organizations_grants_intact(
        self, user, grant, organization, project, environment, make_project
    ):
        other_project = make_project(name="Other Org", key="other-org")
        other_organization = other_project.organization

        org_membership = grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.EDITOR)
        grant(user, environment=environment, role=EnvironmentRole.EDITOR)

        grant(user, org=other_organization, role=OrganizationRole.USER)
        other_project_membership = grant(user, project=other_project, role=ProjectRole.VIEWER)

        org_membership.delete()

        assert not ProjectMembership.objects.filter(
            user=user, project__organization=organization
        ).exists()
        assert not EnvironmentMembership.objects.filter(
            user=user, environment__project__organization=organization
        ).exists()

        # The other organization's grant survives untouched.
        assert ProjectMembership.objects.filter(pk=other_project_membership.pk).exists()

    def test_cascade_runs_via_direct_instance_delete(self, user, grant, organization, project):
        """The DRF view isn't the only caller -- a bare `instance.delete()` must cascade too."""
        org_membership = grant(user, org=organization, role=OrganizationRole.USER)
        project_membership = grant(user, project=project, role=ProjectRole.EDITOR)

        org_membership.delete()

        assert not ProjectMembership.objects.filter(pk=project_membership.pk).exists()


@pytest.mark.django_db
class TestOrphanGrantIsInert:
    """
    Layer 2's own test: an orphan -- built directly through the ORM to
    bypass the serializer's organization-membership prerequisite, with no
    `OrganizationMembership` ever created and no delete ever happening --
    must be inert. This must hold with no Layer 1 cascade in the picture.
    """

    def test_orphaned_project_membership_grants_nothing(self, user, project):
        assert not OrganizationMembership.objects.filter(user=user).exists()
        ProjectMembership.objects.create(project=project, user=user, role=ProjectRole.ADMIN)

        assert not projects_with(user, "project.manage").filter(pk=project.pk).exists()
        assert not environments_with(user, "flag.edit").exists()

    def test_orphaned_environment_membership_grants_nothing(self, user, project, environment):
        assert not OrganizationMembership.objects.filter(user=user).exists()
        EnvironmentMembership.objects.create(environment=environment, user=user, role=EnvironmentRole.ADMIN)

        assert not environments_with(user, "flag.edit").filter(pk=environment.pk).exists()
        # Including the narrow "environment membership implies parent project
        # visibility" special case -- an orphan grants nothing at all, not
        # even that.
        assert not projects_with(user, "project.view").filter(pk=project.pk).exists()

    def test_orphaned_grant_is_invisible_and_unwritable_through_the_api(
        self, api_client, user, project, environment, flag
    ):
        assert not OrganizationMembership.objects.filter(user=user).exists()
        ProjectMembership.objects.create(project=project, user=user, role=ProjectRole.EDITOR)
        client = api_client(user)

        assert client.get("/api/v1/tenancy/projects/").data["results"] == []
        assert client.get("/api/v1/environments/").data["results"] == []
        assert client.get("/api/v1/flags/").data["results"] == []

        response = client.patch(f"/api/v1/flags/{flag.id}/", {"is_enabled": True}, format="json")
        assert response.status_code in (403, 404)


@pytest.mark.django_db
class TestAdminBulkDeleteCascades:
    """
    Layer 1 must survive Django admin's bulk "Delete selected" action, which
    runs `queryset.delete()` and never calls `Model.delete()` on any of the
    collected instances.
    """

    def test_bulk_delete_selected_cascades_project_grants(self, user, grant, organization, project):
        User.objects.create_superuser(
            username="root", email="root@example.com", password="tram-quartz-19-belt"
        )
        org_membership = grant(user, org=organization, role=OrganizationRole.USER)
        project_membership = grant(user, project=project, role=ProjectRole.EDITOR)

        client = Client()
        assert client.login(username="root", password="tram-quartz-19-belt")

        response = client.post(
            reverse("admin:tenancy_organizationmembership_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [str(org_membership.pk)],
                "post": "yes",
            },
        )

        assert response.status_code == 302
        assert not OrganizationMembership.objects.filter(pk=org_membership.pk).exists()
        assert not ProjectMembership.objects.filter(pk=project_membership.pk).exists()
