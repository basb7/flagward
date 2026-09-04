"""
What a plan limits, and what it deliberately does not.

Every ceiling is scoped to an organization, because an organization is where a
subscription lives. How many organizations somebody creates is not limited at
all: an empty one holds no projects, no flags and no traffic, so metering them
would be metering nothing.

COMMUNITY is unlimited on everything. That is what keeps a self-hosted install
unaffected -- a hosted deployment sets DEFAULT_ORGANIZATION_PLAN and nothing
else changes.
"""
import pytest
from django.contrib.auth import get_user_model

from tenancy.models import Organization, OrganizationMembership, OrganizationRole, Plan, Project

ORGANIZATIONS_URL = "/api/v1/tenancy/organizations/"
PROJECTS_URL = "/api/v1/tenancy/projects/"


@pytest.mark.django_db
class TestOrganizationsAreNotLimited:
    def test_a_free_user_creates_as_many_as_they_like(self, api_client, user, settings):
        settings.DEFAULT_ORGANIZATION_PLAN = Plan.FREE
        client = api_client(user)

        for name in ("One", "Two", "Three"):
            assert client.post(ORGANIZATIONS_URL, {"name": name}).status_code == 201

        assert OrganizationMembership.objects.filter(user=user).count() == 3

    def test_administering_somebody_elses_costs_nothing(self, api_client, user, grant, settings):
        """Being invited as an ADMIN is a permission, not a purchase. With no
        ceiling on organizations there is nothing for it to consume, which is
        the point of not having one."""
        settings.DEFAULT_ORGANIZATION_PLAN = Plan.FREE
        theirs = Organization.objects.create(name="Theirs", plan=Plan.FREE)
        grant(user, org=theirs, role=OrganizationRole.ADMIN)

        assert api_client(user).post(ORGANIZATIONS_URL, {"name": "Mine"}).status_code == 201


@pytest.mark.django_db
class TestProjectsPerOrganization:
    def test_a_free_organization_creates_its_first_project(self, api_client, user, grant):
        organization = Organization.objects.create(name="Acme", plan=Plan.FREE)
        grant(user, org=organization, role=OrganizationRole.ADMIN)

        response = api_client(user).post(
            PROJECTS_URL, {"name": "Checkout", "organization": str(organization.id)}
        )

        assert response.status_code == 201

    def test_the_second_one_is_refused(self, api_client, user, grant):
        organization = Organization.objects.create(name="Acme", plan=Plan.FREE)
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)
        client.post(PROJECTS_URL, {"name": "First", "organization": str(organization.id)})

        response = client.post(
            PROJECTS_URL, {"name": "Second", "organization": str(organization.id)}
        )

        assert response.status_code == 400
        assert response.data["error"] == "project_limit_reached"
        assert Project.objects.filter(organization=organization).count() == 1

    def test_the_ceiling_is_per_organization_not_per_user(self, api_client, user, grant):
        """Two FREE organizations get one project each, not one between them."""
        first = Organization.objects.create(name="First", plan=Plan.FREE)
        second = Organization.objects.create(name="Second", plan=Plan.FREE)
        for organization in (first, second):
            grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        for organization in (first, second):
            payload = {"name": "P", "organization": str(organization.id)}
            assert client.post(PROJECTS_URL, payload).status_code == 201

    def test_a_community_organization_has_no_ceiling(self, api_client, user, grant):
        organization = Organization.objects.create(name="Acme", plan=Plan.COMMUNITY)
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        for name in ("One", "Two", "Three"):
            payload = {"name": name, "organization": str(organization.id)}
            assert client.post(PROJECTS_URL, payload).status_code == 201


@pytest.mark.django_db
class TestTheOrganizationsPlan:
    def test_it_comes_from_the_configured_default(self, api_client, user, settings):
        settings.DEFAULT_ORGANIZATION_PLAN = Plan.FREE

        api_client(user).post(ORGANIZATIONS_URL, {"name": "Acme"})

        assert Organization.objects.get(name="Acme").plan == Plan.FREE

    def test_a_self_hosted_install_gets_community(self, api_client, user, settings):
        """Nothing about quotas reaches an operator who sets nothing."""
        settings.DEFAULT_ORGANIZATION_PLAN = Plan.COMMUNITY

        api_client(user).post(ORGANIZATIONS_URL, {"name": "Acme"})

        assert Organization.objects.get(name="Acme").plan == Plan.COMMUNITY

    def test_it_cannot_be_chosen_by_the_caller(self, api_client, user, settings):
        """Otherwise upgrading is a field in a POST body."""
        settings.DEFAULT_ORGANIZATION_PLAN = Plan.FREE

        api_client(user).post(ORGANIZATIONS_URL, {"name": "Acme", "plan": Plan.TEAM})

        assert Organization.objects.get(name="Acme").plan == Plan.FREE

    def test_an_unrecognised_default_is_refused(self, settings):
        settings.DEFAULT_ORGANIZATION_PLAN = "gratis"
        person = get_user_model().objects.create_user(username="n", email="n@e.com", password="x")

        with pytest.raises(Exception, match="DEFAULT_ORGANIZATION_PLAN"):
            Organization.objects.create(name="Acme")

        assert person.pk is not None


@pytest.mark.django_db
class TestFlagsAndConditionsAreNotLimited:
    def test_a_free_organization_holds_as_many_flags_as_it_likes(
        self, user, grant, make_environment, make_flag
    ):
        """The plan limits containers, not what goes in them. A limit that does
        not exist is not written, so this is here to keep it that way."""
        organization = Organization.objects.create(name="Acme", plan=Plan.FREE)
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        project = Project.objects.create(organization=organization, name="P", key="p")
        environment = make_environment(project=project)

        for index in range(25):
            make_flag(environment=environment, key=f"flag-{index}", name=f"Flag {index}")

        assert environment.flags.count() == 25
