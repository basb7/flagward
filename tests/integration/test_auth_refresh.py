"""
Tests for POST /api/v1/auth/refresh/.
"""
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

ACCESS_COOKIE = settings.SIMPLE_JWT['AUTH_COOKIE']
REFRESH_COOKIE = settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH']


@pytest.mark.django_db
class TestRefreshEndpoint:
    """The refresh cookie is what keeps a session alive past the access token."""

    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='admin', email='admin@example.com', password='secret')

    def issue_tokens(self, issued_ago=timedelta(hours=1)):
        """
        Put a valid refresh cookie on the client, as login would.

        The token is backdated because a refresh only matters once time has
        passed: issuing and rotating within the same second produces expiries
        that are equal to the second, which says nothing about rotation.
        """
        refresh = RefreshToken.for_user(self.user)
        refresh.set_exp(from_time=timezone.now() - issued_ago)
        self.client.cookies[REFRESH_COOKIE] = str(refresh)
        return refresh

    def test_refresh_without_a_cookie_is_rejected(self):
        """Nothing to refresh from means unauthorized, not a server error."""
        response = self.client.post('/api/v1/auth/refresh/')

        assert response.status_code == 401

    def test_refresh_with_an_invalid_cookie_is_rejected(self):
        """A malformed or forged token must not mint a new access token."""
        self.client.cookies[REFRESH_COOKIE] = 'not-a-token'

        response = self.client.post('/api/v1/auth/refresh/')

        assert response.status_code == 401

    def test_refresh_issues_a_new_access_cookie(self):
        """A valid refresh cookie mints a fresh access token."""
        self.issue_tokens()

        response = self.client.post('/api/v1/auth/refresh/')

        assert response.status_code == 200
        assert response.cookies[ACCESS_COOKIE].value

    def test_refresh_rotates_the_refresh_token(self):
        """
        ROTATE_REFRESH_TOKENS is on, so the returned refresh token must be a
        genuinely new one. Re-serialising the incoming token returns the same
        string with the same expiry, which would let a session die on the
        original deadline no matter how actively it is used.
        """
        original = self.issue_tokens()

        response = self.client.post('/api/v1/auth/refresh/')

        assert response.status_code == 200

        rotated = RefreshToken(response.cookies[REFRESH_COOKIE].value)
        assert str(rotated) != str(original)
        assert rotated['jti'] != original['jti']
        assert rotated['exp'] > original['exp']

    def test_rotated_token_can_refresh_again(self):
        """The rotated token has to work, or the session breaks on the next hop."""
        self.issue_tokens()

        first = self.client.post('/api/v1/auth/refresh/')
        self.client.cookies[REFRESH_COOKIE] = first.cookies[REFRESH_COOKIE].value
        second = self.client.post('/api/v1/auth/refresh/')

        assert second.status_code == 200


@pytest.mark.django_db
class TestUnauthenticatedStatus:
    """
    An expired access token has to be distinguishable from a permission
    denial, because that status is the only signal the client has to decide
    whether refreshing is worth attempting. DRF takes the WWW-Authenticate
    header from the first authentication class and downgrades 401 to 403 when
    it has none, so the ordering of DEFAULT_AUTHENTICATION_CLASSES decides it.
    """

    def setup_method(self):
        self.client = APIClient()

    def test_request_without_cookies_is_unauthorized(self):
        """No credentials is 401, not 403."""
        response = self.client.get('/api/v1/auth/me/')

        assert response.status_code == 401

    def test_request_with_an_expired_access_cookie_is_unauthorized(self):
        """A token that no longer validates is 401, so the client can refresh."""
        self.client.cookies[ACCESS_COOKIE] = 'expired.or.invalid'

        response = self.client.get('/api/v1/auth/me/')

        assert response.status_code == 401

    def test_protected_resource_is_unauthorized_without_credentials(self):
        """The same holds for the dashboard endpoints, not just /me/."""
        response = self.client.get('/api/v1/flags/')

        assert response.status_code == 401


@pytest.mark.django_db
class TestDjangoSessionDoesNotHijackTheApi:
    """
    Visiting /admin/ leaves a Django session cookie on the same origin. If
    SessionAuthentication is in the stack it authenticates the dashboard's
    requests through that session and starts enforcing CSRF, which the
    frontend never sends, so every unsafe request fails until the user logs
    out of the admin.
    """

    def setup_method(self):
        # The test client disables CSRF checks unless asked to keep them.
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user(username='admin', email='admin@example.com', password='secret')

    def test_login_succeeds_while_a_django_session_is_active(self):
        """A session from the admin must not make the API demand a CSRF token."""
        self.client.force_login(self.user)

        response = self.client.post(
            '/api/v1/auth/login/',
            {'username': 'admin', 'password': 'secret'},
            format='json',
        )

        assert response.status_code == 200

    def test_a_django_session_alone_does_not_authenticate_the_api(self):
        """
        The API is authenticated by the JWT cookie or an API key, never by the
        admin session: holding one must not grant access to dashboard data.
        """
        self.client.force_login(self.user)

        response = self.client.get('/api/v1/flags/')

        assert response.status_code == 401
