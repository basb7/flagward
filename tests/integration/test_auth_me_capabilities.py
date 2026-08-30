"""
Tests for GET /api/v1/auth/me/ carrying the caller's resolved capabilities.

Before this, `/auth/me/` returned only id/username/email, so the dashboard
could not tell "you have no projects yet" (nothing to see) from "you have no
access to any project" (something exists, you cannot see it) -- both looked
identical: zero rows. The fix answers through `resolve_capabilities`, the
exact same pure function `tenancy.scoping.capabilities_for` calls for real
enforcement, so the answer cannot drift from what is actually enforced.

Granularity is per-organization (design note in the bug report): the
dashboard's first question is "can this user create a project in the current
organization", which is decided entirely by organization role -- `PROJECT_CREATE`
is never granted by a project- or environment-level role (see
`tenancy/capabilities.py`), so no project/environment context is needed to
answer it.
"""
import pytest
from django.contrib.auth import get_user_model

from core_flags.models import Environment
from tenancy.capabilities import Capability
from tenancy.models import OrganizationRole, Project
from tenancy.scoping import capabilities_for

User = get_user_model()


@pytest.mark.django_db
class TestAuthMeCapabilities:
    def test_admin_organization_carries_the_full_catalogue(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.get("/api/v1/auth/me/")

        assert response.status_code == 200
        orgs = {row["id"]: row["capabilities"] for row in response.data["organizations"]}
        assert str(organization.id) in orgs
        assert Capability.PROJECT_CREATE in orgs[str(organization.id)]

    def test_plain_member_organization_cannot_create_projects(
        self, api_client, user, grant, organization
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.get("/api/v1/auth/me/")

        assert response.status_code == 200
        orgs = {row["id"]: row["capabilities"] for row in response.data["organizations"]}
        assert orgs[str(organization.id)] == [Capability.ORG_VIEW]

    def test_organization_with_no_membership_is_absent(self, api_client, user, organization):
        client = api_client(user)

        response = client.get("/api/v1/auth/me/")

        assert response.status_code == 200
        org_ids = {row["id"] for row in response.data["organizations"]}
        assert str(organization.id) not in org_ids

    def test_no_memberships_returns_an_empty_list(self, api_client, user):
        client = api_client(user)

        response = client.get("/api/v1/auth/me/")

        assert response.status_code == 200
        assert response.data["organizations"] == []

    @pytest.mark.parametrize("role", [OrganizationRole.ADMIN, OrganizationRole.USER])
    def test_answer_matches_capabilities_for(self, api_client, user, grant, organization, role):
        """
        The non-negotiable: the endpoint must not become a second source of
        truth. With no project/environment membership, `capabilities_for` on
        any environment in the organization reduces to exactly the org-role
        contribution -- the same value `/auth/me/` must report.
        """
        grant(user, org=organization, role=role)
        project = Project.objects.create(organization=organization, name="P", key="p")
        environment = Environment.objects.create(project=project, key="prod", name="Production")
        client = api_client(user)

        response = client.get("/api/v1/auth/me/")

        assert response.status_code == 200
        orgs = {row["id"]: row["capabilities"] for row in response.data["organizations"]}
        expected = sorted(capabilities_for(user, environment))
        assert orgs[str(organization.id)] == expected
