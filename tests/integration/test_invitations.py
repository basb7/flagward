"""
Tests for single-use organization invitation links (spec: an admin brings
someone into an organization without setting that person's password).

Covers the `Invitation` model's token hashing plus the full
create/list/revoke/preview/accept surface in `tenancy/api/`.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenancy.models import Invitation, Organization, OrganizationMembership, OrganizationRole

User = get_user_model()


@pytest.fixture
def issue_invitation():
    """Callable building an Invitation row directly, bypassing the API."""

    def _issue(*, organization, role=OrganizationRole.USER, created_by=None, ttl=timedelta(days=7)):
        return Invitation.issue(organization=organization, role=role, created_by=created_by, ttl=ttl)

    return _issue


@pytest.mark.django_db
class TestInvitationModel:
    """The token is a bearer credential and must never be recoverable from the row."""

    def test_token_is_not_stored_in_plaintext(self, organization, user):
        invitation, raw_token = Invitation.issue(organization=organization, role=OrganizationRole.USER, created_by=user)

        assert invitation.token_hash != raw_token
        assert raw_token not in invitation.token_hash

    def test_for_token_resolves_the_issued_token(self, organization, user):
        invitation, raw_token = Invitation.issue(organization=organization, role=OrganizationRole.USER, created_by=user)

        assert Invitation.for_token(raw_token) == invitation

    def test_for_token_rejects_an_unknown_token(self):
        assert Invitation.for_token("not-a-real-token") is None

    def test_is_expired_reflects_expiry(self, organization, user):
        invitation, _ = Invitation.issue(
            organization=organization, role=OrganizationRole.USER, created_by=user, ttl=timedelta(days=-1)
        )

        assert invitation.is_expired is True


@pytest.mark.django_db
class TestInvitationCreate:
    def test_admin_creates_invitation_and_receives_a_one_time_token(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/invitations/",
            {"organization": str(organization.id), "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code == 201
        assert "token" in response.data and response.data["token"]
        assert Invitation.objects.filter(organization=organization).count() == 1

    def test_non_privileged_cannot_create_invitation(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/invitations/",
            {"organization": str(organization.id), "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code in (400, 403)
        assert Invitation.objects.count() == 0

    def test_cannot_create_invitation_in_a_foreign_organization(self, api_client, user):
        foreign_org = Organization.objects.create(name="Foreign", plan="COMMUNITY")
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/invitations/",
            {"organization": str(foreign_org.id), "role": OrganizationRole.USER},
            format="json",
        )

        assert response.status_code in (400, 403)
        assert Invitation.objects.count() == 0


@pytest.mark.django_db
class TestInvitationListAndRevoke:
    def test_admin_lists_pending_invitations(self, api_client, user, grant, organization, issue_invitation):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        issue_invitation(organization=organization, created_by=user)
        client = api_client(user)

        response = client.get("/api/v1/tenancy/invitations/")

        assert response.status_code == 200
        assert response.data["count"] == 1

    def test_cannot_list_a_foreign_organization_invitations(
        self, api_client, user, grant, organization, issue_invitation
    ):
        foreign_org = Organization.objects.create(name="Foreign", plan="COMMUNITY")
        issue_invitation(organization=foreign_org, created_by=None)
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.get("/api/v1/tenancy/invitations/")

        assert response.data["count"] == 0

    def test_admin_revokes_a_pending_invitation(self, api_client, user, grant, organization, issue_invitation):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        invitation, _ = issue_invitation(organization=organization, created_by=user)
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{invitation.id}/revoke/")

        assert response.status_code == 200
        invitation.refresh_from_db()
        assert invitation.revoked_at is not None

    def test_cannot_revoke_a_foreign_organization_invitation(
        self, api_client, user, grant, organization, issue_invitation
    ):
        foreign_org = Organization.objects.create(name="Foreign", plan="COMMUNITY")
        invitation, _ = issue_invitation(organization=foreign_org, created_by=None)
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{invitation.id}/revoke/")

        assert response.status_code == 404
        invitation.refresh_from_db()
        assert invitation.revoked_at is None


@pytest.mark.django_db
class TestInvitationPreview:
    def test_preview_is_reachable_without_authentication(self, client, organization, issue_invitation):
        _, raw_token = issue_invitation(organization=organization, role=OrganizationRole.USER, created_by=None)

        response = client.get(f"/api/v1/tenancy/invitations/{raw_token}/preview/")

        assert response.status_code == 200
        assert response.data == {"organization_name": organization.name, "role": OrganizationRole.USER}

    def test_preview_of_an_unknown_token_is_a_generic_404(self, client):
        response = client.get("/api/v1/tenancy/invitations/not-a-real-token/preview/")

        assert response.status_code == 404

    def test_preview_of_an_expired_token_is_the_same_generic_404(self, client, organization, issue_invitation):
        _, raw_token = issue_invitation(organization=organization, ttl=timedelta(days=-1))
        unknown_response = client.get("/api/v1/tenancy/invitations/not-a-real-token/preview/")

        response = client.get(f"/api/v1/tenancy/invitations/{raw_token}/preview/")

        assert response.status_code == unknown_response.status_code == 404
        assert response.data == unknown_response.data

    def test_preview_of_a_revoked_token_is_the_same_generic_404(self, client, organization, issue_invitation):
        invitation, raw_token = issue_invitation(organization=organization)
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])

        response = client.get(f"/api/v1/tenancy/invitations/{raw_token}/preview/")

        assert response.status_code == 404


@pytest.mark.django_db
class TestInvitationAccept:
    def test_accept_joins_the_organization_with_the_invited_role(
        self, api_client, user, organization, issue_invitation
    ):
        _, raw_token = issue_invitation(organization=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code == 201
        membership = OrganizationMembership.objects.get(organization=organization, user=user)
        assert membership.role == OrganizationRole.ADMIN

    def test_accepting_marks_the_invitation_used(self, api_client, user, organization, issue_invitation):
        invitation, raw_token = issue_invitation(organization=organization)
        client = api_client(user)

        client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        invitation.refresh_from_db()
        assert invitation.accepted_by_id == user.id
        assert invitation.accepted_at is not None

    def test_second_accept_fails_distinguishably(self, api_client, user, organization, issue_invitation):
        _, raw_token = issue_invitation(organization=organization)
        first_user = api_client(user)
        first_user.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")
        second_user = User.objects.create_user(username="second", password="tram-quartz-19-belt")
        client = api_client(second_user)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code == 409
        assert response.data["error"] == "invitation_already_used"
        assert not OrganizationMembership.objects.filter(organization=organization, user=second_user).exists()

    def test_expired_invitation_fails_distinguishably(self, api_client, user, organization, issue_invitation):
        _, raw_token = issue_invitation(organization=organization, ttl=timedelta(days=-1))
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code == 410
        assert response.data["error"] == "invitation_expired"

    def test_revoked_invitation_fails_distinguishably(self, api_client, user, organization, issue_invitation):
        invitation, raw_token = issue_invitation(organization=organization)
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code == 410
        assert response.data["error"] == "invitation_revoked"

    def test_unknown_token_fails_distinguishably(self, api_client, user):
        client = api_client(user)

        response = client.post("/api/v1/tenancy/invitations/not-a-real-token/accept/")

        assert response.status_code == 404
        assert response.data["error"] == "invitation_not_found"

    def test_accept_requires_authentication(self, client, organization, issue_invitation):
        _, raw_token = issue_invitation(organization=organization)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code in (401, 403)

    def test_already_a_member_cannot_accept_again(self, api_client, user, grant, organization, issue_invitation):
        grant(user, org=organization, role=OrganizationRole.USER)
        _, raw_token = issue_invitation(organization=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code == 409
        assert response.data["error"] == "already_a_member"
        membership = OrganizationMembership.objects.get(organization=organization, user=user)
        assert membership.role == OrganizationRole.USER  # unchanged

    def test_existing_user_in_another_org_can_accept_and_end_up_in_both(
        self, api_client, user, grant, organization, make_project, issue_invitation
    ):
        other_org = Organization.objects.create(name="Other Co", plan="COMMUNITY")
        grant(user, org=other_org, role=OrganizationRole.USER)
        _, raw_token = issue_invitation(organization=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code == 201
        assert OrganizationMembership.objects.filter(user=user).count() == 2

    def test_seat_limit_enforced_at_accept(self, api_client, user, issue_invitation):
        organization = Organization.objects.create(name="Starter Co", plan="STARTER")
        members = User.objects.bulk_create(User(username=f"seat{i}", password="!") for i in range(5))
        OrganizationMembership.objects.bulk_create(
            OrganizationMembership(organization=organization, user=member, role=OrganizationRole.USER)
            for member in members
        )
        _, raw_token = issue_invitation(organization=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        assert response.status_code == 400
        assert response.data["error"] == "seat_limit_reached"
        assert not OrganizationMembership.objects.filter(organization=organization, user=user).exists()

    def test_seat_limit_does_not_consume_the_invitation(self, api_client, user, issue_invitation):
        """A rejected accept (seat limit) must leave the invitation usable."""
        organization = Organization.objects.create(name="Starter Co", plan="STARTER")
        members = User.objects.bulk_create(User(username=f"full{i}", password="!") for i in range(5))
        OrganizationMembership.objects.bulk_create(
            OrganizationMembership(organization=organization, user=member, role=OrganizationRole.USER)
            for member in members
        )
        invitation, raw_token = issue_invitation(organization=organization, role=OrganizationRole.USER)
        client = api_client(user)

        client.post(f"/api/v1/tenancy/invitations/{raw_token}/accept/")

        invitation.refresh_from_db()
        assert invitation.accepted_at is None
