"""
Tests for POST /api/v1/auth/register/ (spec: organization-management --
Self-Registration Creates Only the User). Registration used to
auto-provision an organization named after the username; that decision is
reversed here -- the person names their own first organization from the
dashboard's empty state instead.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tenancy.models import Organization

User = get_user_model()


@pytest.mark.django_db
class TestRegistrationCreatesNoOrganization:
    def setup_method(self):
        self.client = APIClient()

    def test_registration_creates_a_user_and_no_organization(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {"username": "newuser", "email": "new@example.com", "password": "tram-quartz-19-belt"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["user"]["username"] == "newuser"
        assert Organization.objects.count() == 0


@pytest.mark.django_db
class TestPasswordPolicyIsEnforced:
    """
    `AUTH_PASSWORD_VALIDATORS` (settings.py) is configured with four
    validators, but Django only applies them where `validate_password` is
    called. Nothing called it: registration accepted a one-character password
    and member creation checked length alone, so the common-password and
    numeric-only validators the project had already chosen never ran.

    These tests fail if that wiring is removed again -- a configured policy
    that nothing enforces looks exactly like a policy that works.
    """

    def _register(self, password):
        return APIClient().post(
            "/api/v1/auth/register/",
            {"username": "newcomer", "email": "n@example.com", "password": password},
            format="json",
        )

    def test_a_one_character_password_is_rejected(self):
        response = self._register("a")

        assert response.status_code == 400
        assert "password" in response.data
        assert not User.objects.filter(username="newcomer").exists()

    def test_a_purely_numeric_password_is_rejected(self):
        """Eight characters, so length alone would have let this through."""
        response = self._register("12345678")

        assert response.status_code == 400
        assert not User.objects.filter(username="newcomer").exists()

    def test_a_common_password_is_rejected(self):
        response = self._register("password123")

        assert response.status_code == 400
        assert not User.objects.filter(username="newcomer").exists()

    def test_a_password_resembling_the_username_is_rejected(self):
        response = APIClient().post(
            "/api/v1/auth/register/",
            {"username": "constantine", "email": "c@example.com", "password": "constantine1"},
            format="json",
        )

        assert response.status_code == 400
        assert not User.objects.filter(username="constantine").exists()

    def test_a_sound_password_is_accepted(self):
        response = self._register("tram-quartz-19-belt")

        assert response.status_code == 201
        assert User.objects.filter(username="newcomer").exists()
