"""
Tests for the Organization Administration Invariant (spec/tenancy-model):
an organization must never reach zero `ADMIN` memberships, enforced on both
`OrganizationMembership` delete and role-demote (tasks 6.8/6.9).
"""
import pytest
from django.contrib.auth import get_user_model

from tenancy.models import OrganizationMembership, OrganizationRole

User = get_user_model()


@pytest.mark.django_db
class TestAdministrationInvariant:
    def test_last_admin_cannot_be_removed(self, api_client, user, grant, organization):
        membership = grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/organization-memberships/{membership.id}/")

        assert response.status_code == 400
        assert OrganizationMembership.objects.filter(pk=membership.pk).exists()

    def test_last_admin_cannot_be_demoted(self, api_client, user, grant, organization):
        membership = grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/organization-memberships/{membership.id}/",
            {"role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 400
        membership.refresh_from_db()
        assert membership.role == OrganizationRole.ADMIN

    def test_non_last_admin_can_be_removed(self, api_client, user, grant, organization):
        """Triangulation: the invariant only blocks the *last* admin."""
        membership = grant(user, org=organization, role=OrganizationRole.ADMIN)
        second_admin = User.objects.create_user(username="second-admin", password="secret")
        grant(second_admin, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/organization-memberships/{membership.id}/")

        assert response.status_code == 204
        assert not OrganizationMembership.objects.filter(pk=membership.pk).exists()

    def test_non_privileged_member_cannot_remove_a_membership(self, api_client, user, grant, organization):
        """A `USER`-role member has no `org.manage_members` capability -- 403."""
        membership = grant(user, org=organization, role=OrganizationRole.ADMIN)
        member = User.objects.create_user(username="member", password="secret")
        grant(member, org=organization, role=OrganizationRole.USER)
        client = api_client(member)

        response = client.delete(f"/api/v1/tenancy/organization-memberships/{membership.id}/")

        assert response.status_code == 403
        assert OrganizationMembership.objects.filter(pk=membership.pk).exists()

    def test_promoting_a_member_to_admin_is_unaffected_by_the_invariant(
        self, api_client, user, grant, organization
    ):
        """Triangulation: the invariant only blocks a demotion/removal, never a promotion."""
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        member = User.objects.create_user(username="member", password="secret")
        member_membership = grant(member, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/organization-memberships/{member_membership.id}/",
            {"role": OrganizationRole.ADMIN},
            format="json",
        )

        assert response.status_code == 200
        member_membership.refresh_from_db()
        assert member_membership.role == OrganizationRole.ADMIN
