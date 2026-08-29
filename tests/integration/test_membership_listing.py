"""
Tests for GET on the organization/project/environment membership collections
(tasks 8.2/8.3). Slice 6 shipped Create-only (project/environment) and
Update+Destroy-only (organization) viewsets -- none included `ListModelMixin`,
so the members screen could create members and grants but never enumerate
them. Each collection is scoped by the same `<level>__in=<scoping helper>`
subquery idiom `OrganizationMembershipViewSet.get_queryset` already used
(design D4) -- no `.distinct()`, and the FROM table is the membership table
itself, so `assert_membership_never_joined` (which targets scoping-helper
querysets over Organization/Project/Environment, not membership rows) does
not apply here; the foreign-tenant-absent scenario below is the correct proof
for a queryset whose own model already carries `user` and `role` columns.

Read capability, chosen deliberately: listing uses the *view* capability at
each level (`ORG_VIEW` / `PROJECT_VIEW` / `ENVIRONMENT_VIEW`), not the
*manage_members* capability the create/update/destroy actions already
enforce. Seeing who else shares your organization, project, or environment is
ordinary visibility, not administration -- the same split
`OrganizationMembershipViewSet` already draws between its (view-scoped)
`get_queryset` and its `_require_manage_permission`-gated mutations.
"""
import pytest
from django.contrib.auth import get_user_model

from tenancy.models import (
    EnvironmentMembership,
    EnvironmentRole,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    ProjectMembership,
    ProjectRole,
)

User = get_user_model()


@pytest.mark.django_db
class TestOrganizationMembershipListing:
    """task 8.2/8.3: GET /api/v1/tenancy/organization-memberships/."""

    def test_lists_own_organization_members_only(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        foreign_org = Organization.objects.create(name="Foreign", plan="COMMUNITY")
        foreign_user = type(user).objects.create_user(username="foreign-admin", password="!")
        OrganizationMembership.objects.create(
            organization=foreign_org, user=foreign_user, role=OrganizationRole.ADMIN
        )
        client = api_client(user)

        response = client.get("/api/v1/tenancy/organization-memberships/")

        assert response.status_code == 200
        # `organization` is a FK (`PrimaryKeyRelatedField`), whose
        # `to_representation` returns the raw `value.pk` -- a UUID instance,
        # not a stringified one (unlike `id`, an actual `UUIDField` whose
        # `to_representation` does call `str()`).
        org_ids = {row["organization"] for row in response.data["results"]}
        assert org_ids == {organization.id}

    def test_no_membership_anywhere_sees_no_rows(self, api_client, user):
        client = api_client(user)

        response = client.get("/api/v1/tenancy/organization-memberships/")

        assert response.status_code == 200
        assert response.data["results"] == []


@pytest.mark.django_db
class TestProjectMembershipListing:
    """task 8.2/8.3: GET /api/v1/tenancy/project-memberships/."""

    def test_lists_own_project_members_only(self, api_client, user, grant, project, make_project):
        membership = grant(user, project=project, role=ProjectRole.VIEWER)
        foreign_project = make_project(name="Foreign", key="foreign")
        foreign_user = type(user).objects.create_user(username="foreign-editor", password="!")
        ProjectMembership.objects.create(
            project=foreign_project, user=foreign_user, role=ProjectRole.EDITOR
        )
        client = api_client(user)

        response = client.get("/api/v1/tenancy/project-memberships/")

        assert response.status_code == 200
        ids = {row["id"] for row in response.data["results"]}
        assert ids == {str(membership.id)}

    def test_no_membership_anywhere_sees_no_rows(self, api_client, user):
        client = api_client(user)

        response = client.get("/api/v1/tenancy/project-memberships/")

        assert response.status_code == 200
        assert response.data["results"] == []


@pytest.mark.django_db
class TestEnvironmentMembershipListing:
    """task 8.2/8.3: GET /api/v1/tenancy/environment-memberships/."""

    def test_lists_own_environment_members_only(
        self, api_client, user, grant, environment, make_project, make_environment
    ):
        membership = grant(user, environment=environment, role=EnvironmentRole.VIEWER)
        foreign_project = make_project(name="Foreign", key="foreign")
        foreign_environment = make_environment(project=foreign_project, key="stage", name="Staging")
        foreign_user = type(user).objects.create_user(username="foreign-viewer", password="!")
        EnvironmentMembership.objects.create(
            environment=foreign_environment, user=foreign_user, role=EnvironmentRole.VIEWER
        )
        client = api_client(user)

        response = client.get("/api/v1/tenancy/environment-memberships/")

        assert response.status_code == 200
        ids = {row["id"] for row in response.data["results"]}
        assert ids == {str(membership.id)}

    def test_no_membership_anywhere_sees_no_rows(self, api_client, user):
        client = api_client(user)

        response = client.get("/api/v1/tenancy/environment-memberships/")

        assert response.status_code == 200
        assert response.data["results"] == []


@pytest.mark.django_db
class TestMembershipListingNamesPeople:
    """
    A members screen has to name people. A bare `user` pk names nobody, and
    the API exposes no user-detail endpoint to resolve one against, so the
    username travels with the membership row or not at all.
    """

    def test_organization_membership_list_carries_the_username(
        self, api_client, user, grant, organization
    ):
        grant(user, org=organization, role=OrganizationRole.ADMIN)

        response = api_client(user).get("/api/v1/tenancy/organization-memberships/")

        assert response.status_code == 200
        assert response.data["results"][0]["username"] == user.username

    def test_listing_costs_one_query_per_page_not_one_per_member(
        self, api_client, user, grant, organization, django_assert_max_num_queries
    ):
        """
        `username` reads through the membership's user relation, so without
        select_related each row would fetch its own. The count below is a
        ceiling, not a target -- it fails loudly if a future change
        reintroduces the per-row query.
        """
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        others = User.objects.bulk_create(
            User(username=f"member{i}", password="!") for i in range(10)
        )
        OrganizationMembership.objects.bulk_create(
            OrganizationMembership(
                organization=organization, user=other, role=OrganizationRole.USER
            )
            for other in others
        )
        client = api_client(user)

        with django_assert_max_num_queries(8):
            response = client.get("/api/v1/tenancy/organization-memberships/")

        assert response.status_code == 200
        assert len(response.data["results"]) == 11
