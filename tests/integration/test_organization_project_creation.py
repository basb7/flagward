"""
Tests for POST /api/v1/tenancy/organizations/ and POST /api/v1/tenancy/projects/
(spec/organization-management; design D5, Layer 2 -- the only create-time gate
for `Project.organization`).

`OrganizationViewSet.create` has no capability to check and no FK to narrow:
an organization has no parent tenant. `ProjectViewSet.create` narrows the
`organization` FK through `CapabilityScopedFKMixin` to organizations where the
requester holds `Capability.PROJECT_CREATE` -- an unnarrowed FK here would
reopen exactly the root-level hole the tenancy change closed (F3), one level
above it.
"""
import pytest

from tenancy.models import Organization, OrganizationMembership, OrganizationRole, Project


@pytest.mark.django_db
class TestOrganizationCreate:
    def test_any_authenticated_user_creates_an_organization_and_becomes_its_admin(
        self, api_client, user
    ):
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/organizations/", {"name": "Acme"}, format="json"
        )

        assert response.status_code == 201
        organization = Organization.objects.get(id=response.data["id"])
        assert organization.name == "Acme"
        membership = OrganizationMembership.objects.get(organization=organization, user=user)
        assert membership.role == OrganizationRole.ADMIN


@pytest.mark.django_db
class TestProjectCreate:
    def test_org_admin_creates_a_project(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/projects/",
            {"organization": str(organization.id), "name": "Checkout", "key": "checkout"},
            format="json",
        )

        assert response.status_code == 201
        assert Project.objects.filter(organization=organization, key="checkout").exists()

    def test_cross_tenant_project_create_returns_400_and_creates_nothing(
        self, api_client, user, grant, organization, make_project
    ):
        # `user` administers a *different* organization -- never the one it
        # targets below.
        own_organization = make_project(name="Own", key="own").organization
        grant(user, org=own_organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/projects/",
            {"organization": str(organization.id), "name": "Planted", "key": "planted"},
            format="json",
        )

        assert response.status_code == 400
        assert not Project.objects.filter(key="planted").exists()

    def test_org_user_without_project_create_capability_is_rejected(
        self, api_client, user, grant, organization
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/projects/",
            {"organization": str(organization.id), "name": "Checkout", "key": "checkout"},
            format="json",
        )

        assert response.status_code == 400
        assert not Project.objects.filter(key="checkout").exists()

    def test_duplicate_project_key_in_same_organization_returns_400(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/projects/",
            {"organization": str(organization.id), "name": "Duplicate", "key": project.key},
            format="json",
        )

        assert response.status_code == 400
        assert Project.objects.filter(organization=organization, key=project.key).count() == 1


@pytest.mark.django_db
class TestNoSuperuserBypassOnCreation:
    """
    spec/access-control: No Superuser Bypass, extended to the two new write
    paths (see `tests.integration.test_tenant_scoping.TestNoSuperuserBypass`).
    """

    def _superuser_without_membership(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_superuser(
            username="root", password="secret", email="root@example.com"
        )

    def test_superuser_creating_an_organization_gets_no_visibility_into_others(
        self, organization
    ):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.post(
            "/api/v1/tenancy/organizations/", {"name": "Root's Org"}, format="json"
        )

        assert response.status_code == 201
        list_response = client.get("/api/v1/tenancy/organizations/")
        ids = {row["id"] for row in list_response.data["results"]}
        assert str(organization.id) not in ids

    def test_superuser_cannot_create_project_in_a_foreign_organization(self, organization):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.post(
            "/api/v1/tenancy/projects/",
            {"organization": str(organization.id), "name": "Planted", "key": "planted"},
            format="json",
        )

        assert response.status_code == 400
        assert not Project.objects.filter(key="planted").exists()
