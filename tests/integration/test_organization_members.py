"""
Tests for POST /api/v1/tenancy/organizations/{id}/members/ (spec:
organization-management — An Admin Creates and Attaches Users, Seat
Accounting Against the Plan).
"""
import pytest
from django.contrib.auth import get_user_model

from tenancy.models import Organization, OrganizationMembership, OrganizationRole

User = get_user_model()


def _fill_seats(organization, count, start=0, role=OrganizationRole.USER):
    """
    Create `count` extra OrganizationMembership rows, each with a fresh user.

    These users exist to occupy seats and never authenticate, so they are built
    without a usable password. `create_user` would run the real password hasher
    once per row -- at 500 rows that is a minute of PBKDF2 spent proving that a
    counter counts.
    """
    members = User.objects.bulk_create(
        User(username=f"seat{i}", password="!") for i in range(start, start + count)
    )
    OrganizationMembership.objects.bulk_create(
        OrganizationMembership(organization=organization, user=member, role=role)
        for member in members
    )


@pytest.mark.django_db
class TestAdminCreatesMember:
    """spec: An Admin Creates and Attaches Users (tasks 6.3/6.5)."""

    def test_admin_creates_member(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {
                "username": "newmember",
                "email": "member@example.com",
                "password": "tram-quartz-19-belt",
                "role": OrganizationRole.USER,
            },
            format="json",
        )

        assert response.status_code == 201
        assert OrganizationMembership.objects.filter(
            organization=organization, user__username="newmember", role=OrganizationRole.USER
        ).exists()

    def test_non_privileged_cannot_create_member(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {
                "username": "newmember",
                "email": "member@example.com",
                "password": "tram-quartz-19-belt",
                "role": OrganizationRole.USER,
            },
            format="json",
        )

        assert response.status_code == 403
        assert not User.objects.filter(username="newmember").exists()

    def test_cannot_create_member_in_a_foreign_organization(self, api_client, user, grant, make_project):
        """A user with no membership in the target org gets 404, not 403 -- Layer 1."""
        foreign_org = Organization.objects.create(name="Foreign", plan="COMMUNITY")
        client = api_client(user)

        response = client.post(
            f"/api/v1/tenancy/organizations/{foreign_org.id}/members/",
            {"username": "intruder", "password": "tram-quartz-19-belt", "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestSeatAccounting:
    """spec: Seat Accounting Against the Plan (task 6.4)."""

    def test_under_the_limit_creates(self, api_client, user, grant):
        organization = Organization.objects.create(name="Starter Co", plan="STARTER")
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        _fill_seats(organization, 3)  # admin + 3 = 4 memberships, limit 5
        client = api_client(user)

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {"username": "fifth", "password": "tram-quartz-19-belt", "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 201
        assert OrganizationMembership.objects.filter(organization=organization).count() == 5

    def test_at_the_boundary_rejects(self, api_client, user, grant):
        organization = Organization.objects.create(name="Starter Co", plan="STARTER")
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        _fill_seats(organization, 4)  # admin + 4 = 5 memberships == limit
        client = api_client(user)

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {"username": "sixth", "password": "tram-quartz-19-belt", "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["error"] == "seat_limit_reached"
        assert not User.objects.filter(username="sixth").exists()
        assert OrganizationMembership.objects.filter(organization=organization).count() == 5

    def test_community_plan_never_blocks(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        _fill_seats(organization, 500)
        client = api_client(user)

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {"username": "member501", "password": "tram-quartz-19-belt", "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 201

    def test_removing_a_member_frees_the_seat_immediately(self, api_client, user, grant):
        organization = Organization.objects.create(name="Starter Co", plan="STARTER")
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        _fill_seats(organization, 4)  # at the limit (5)
        client = api_client(user)
        victim = OrganizationMembership.objects.filter(organization=organization).exclude(user=user).first()
        victim.delete()

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {"username": "replacement", "password": "tram-quartz-19-belt", "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 201

    def test_deactivated_user_still_counts_toward_the_limit(self, api_client, user, grant):
        organization = Organization.objects.create(name="Starter Co", plan="STARTER")
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        _fill_seats(organization, 4)  # at the limit (5)
        deactivated = (
            OrganizationMembership.objects.filter(organization=organization).exclude(user=user).first().user
        )
        deactivated.is_active = False
        deactivated.save()
        client = api_client(user)

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {"username": "overflow", "password": "tram-quartz-19-belt", "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["error"] == "seat_limit_reached"

    def test_plan_downgrade_does_not_evict_existing_members_but_blocks_new_ones(
        self, api_client, user, grant
    ):
        organization = Organization.objects.create(name="Big Co", plan="TEAM")
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        _fill_seats(organization, 7)  # admin + 7 = 8 memberships, well under TEAM's 25
        organization.plan = "STARTER"  # limit drops to 5, below the current 8
        organization.save()
        client = api_client(user)

        assert OrganizationMembership.objects.filter(organization=organization).count() == 8

        response = client.post(
            f"/api/v1/tenancy/organizations/{organization.id}/members/",
            {"username": "ninth", "password": "tram-quartz-19-belt", "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["error"] == "seat_limit_reached"
        assert OrganizationMembership.objects.filter(organization=organization).count() == 8
