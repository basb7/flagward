"""
Tests for POST /api/v1/auth/register/ auto-provisioning an organization
(spec: organization-management — Self-Registration Auto-Provisions an
Organization).
"""
import pytest
from rest_framework.test import APIClient

from tenancy.models import Organization, OrganizationMembership, OrganizationRole


@pytest.mark.django_db
class TestRegistrationAutoProvisionsOrganization:
    def setup_method(self):
        self.client = APIClient()

    def test_registration_auto_provisions_organization(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {"username": "newuser", "email": "new@example.com", "password": "password123"},
            format="json",
        )

        assert response.status_code == 201
        user_id = response.data["user"]["id"]

        assert Organization.objects.count() == 1
        membership = OrganizationMembership.objects.get(user_id=user_id)
        assert membership.role == OrganizationRole.ADMIN
        assert membership.organization == Organization.objects.first()
