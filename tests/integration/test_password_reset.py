"""
Tests for the password-reset flow: POST /api/v1/auth/password-reset/request/,
POST /api/v1/auth/password-reset/confirm/, and GET /api/v1/auth/config/.

The token follows tenancy.models.Invitation's shape (hashed at rest, plaintext
only in the outgoing message, single use, short expiry) -- see
authentication/models.py's PasswordResetToken for the reasoning that differs
from Invitation (shorter TTL, no "revoked" state).

The request endpoint answers identically whether or not an account exists for
the submitted email, for the same reason InvitationPreviewView answers a
single generic 404 (see tenancy/api/views.py): telling the two cases apart
turns the endpoint into an account-existence oracle.
"""
import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APIClient

from authentication.models import PasswordResetToken

User = get_user_model()

ACCESS_COOKIE = settings.SIMPLE_JWT["AUTH_COOKIE"]
REFRESH_COOKIE = settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"]

REQUEST_URL = "/api/v1/auth/password-reset/request/"
CONFIRM_URL = "/api/v1/auth/password-reset/confirm/"
CONFIG_URL = "/api/v1/auth/config/"

STRONG_PASSWORD = "tram-quartz-19-belt"


def _raw_token_from_reset_email_body(body):
    """Pull the raw token back out of a sent reset email's `/reset-password/<token>` link."""
    match = re.search(r"/reset-password/(\S+)", body)
    assert match, f"no reset-password link found in email body: {body!r}"
    return match.group(1)


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """
    The rate-limit throttle is backed by the default cache, which is not
    reset between tests by Django's per-test transaction rollback (it is not
    the database). Left alone, an early test's requests would count against
    a later test's rate limit.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user():
    return User.objects.create_user(username="dash", email="dash@example.com", password="original-pw-1")


@pytest.mark.django_db
class TestPasswordResetRequest:
    def test_a_request_for_a_real_address_produces_a_usable_token(self, user):
        response = APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")

        assert response.status_code == 200
        token = PasswordResetToken.objects.get(user=user)
        assert token.is_expired is False
        assert token.is_used is False

    def test_a_request_for_a_real_address_sends_an_email_with_a_usable_token(self, user, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

        APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["dash@example.com"]

    def test_the_email_carries_a_clickable_reset_link_built_from_the_frontend_setting(self, user, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.FRONTEND_BASE_URL = "https://app.example.com"

        APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")

        token = PasswordResetToken.objects.get(user=user)
        body = mail.outbox[0].body
        # The link must be built from the raw token, not the stored hash --
        # the hash is what `for_token` looks up by, but it is not the bearer
        # credential a person pastes into their browser.
        assert token.token_hash not in body
        raw_token = _raw_token_from_reset_email_body(body)
        assert f"https://app.example.com/reset-password/{raw_token}" in body
        confirm = APIClient().post(CONFIRM_URL, {"token": raw_token, "password": STRONG_PASSWORD}, format="json")
        assert confirm.status_code == 200

    def test_the_email_states_the_link_is_single_use_and_expires_in_one_hour(self, user, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

        APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")

        body = mail.outbox[0].body
        assert "one hour" in body
        assert "once" in body

    def test_the_email_still_reassures_an_unrequested_recipient_they_can_ignore_it(self, user, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

        APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")

        assert "ignore this email" in mail.outbox[0].body

    def test_a_trailing_slash_on_frontend_base_url_does_not_double_the_slash_in_the_link(self, user, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.FRONTEND_BASE_URL = "https://app.example.com/"

        APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")

        body = mail.outbox[0].body
        assert "app.example.com//" not in body
        raw_token = _raw_token_from_reset_email_body(body)
        assert f"https://app.example.com/reset-password/{raw_token}" in body

    def test_a_malformed_frontend_base_url_still_sends_a_usable_non_crashing_message(self, user, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.FRONTEND_BASE_URL = "not-a-url"

        response = APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert "not-a-url/reset-password/" in mail.outbox[0].body

    def test_a_request_for_an_unknown_address_answers_identically_and_creates_nothing(self):
        real_response = APIClient().post(REQUEST_URL, {"email": "unknown@example.com"}, format="json")

        assert real_response.status_code == 200
        assert PasswordResetToken.objects.count() == 0

    def test_known_and_unknown_addresses_get_the_same_response_body(self, user):
        known = APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json")
        cache.clear()  # a second address must not be throttled by the first
        unknown = APIClient().post(REQUEST_URL, {"email": "nobody@example.com"}, format="json")

        assert known.status_code == unknown.status_code
        assert known.data == unknown.data

    def test_a_placeholder_email_from_the_email_migration_produces_no_token(self):
        """
        A `@no-email.invalid` placeholder (authentication/migrations/
        0001_email_required_unique.py) cannot receive anything -- there is no
        real mailbox behind it. The request must still answer the same generic
        way, but must not create a token nobody can ever retrieve.
        """
        placeholder = User.objects.create_user(
            username="legacy", email="user-999@no-email.invalid", password="original-pw-1"
        )

        response = APIClient().post(REQUEST_URL, {"email": placeholder.email}, format="json")

        assert response.status_code == 200
        assert PasswordResetToken.objects.filter(user=placeholder).count() == 0

    def test_a_missing_email_is_rejected_with_a_400(self):
        response = APIClient().post(REQUEST_URL, {}, format="json")

        assert response.status_code == 400

    def test_a_malformed_email_is_rejected_with_a_400(self):
        response = APIClient().post(REQUEST_URL, {"email": "not-an-email"}, format="json")

        assert response.status_code == 400

    def test_email_matching_is_case_insensitive(self, user):
        response = APIClient().post(REQUEST_URL, {"email": "Dash@Example.com"}, format="json")

        assert response.status_code == 200
        assert PasswordResetToken.objects.filter(user=user).count() == 1

    def test_repeated_requests_for_the_same_address_are_rate_limited(self, user):
        """
        Simple, per-target-address throttling: it stops one attacker from
        flooding a single mailbox with reset emails. It does NOT stop an
        attacker who spreads requests across many different target addresses,
        and it does not equalise response timing between a known and unknown
        address -- both are documented limitations, not gaps in this test.
        """
        rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["password_reset_request"]
        limit = int(rate.split("/")[0])

        statuses = [
            APIClient().post(REQUEST_URL, {"email": "dash@example.com"}, format="json").status_code
            for _ in range(limit + 1)
        ]

        assert statuses[:limit] == [200] * limit
        assert statuses[-1] == 429


@pytest.mark.django_db
class TestPasswordResetConfirm:
    def test_the_token_resets_the_password_and_the_old_one_stops_working(self, user):
        token, raw_token = PasswordResetToken.issue(user=user)

        response = APIClient().post(
            CONFIRM_URL, {"token": raw_token, "password": STRONG_PASSWORD}, format="json"
        )

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password(STRONG_PASSWORD) is True
        assert user.check_password("original-pw-1") is False

    def test_a_second_use_of_the_same_token_fails(self, user):
        token, raw_token = PasswordResetToken.issue(user=user)
        first = APIClient().post(CONFIRM_URL, {"token": raw_token, "password": STRONG_PASSWORD}, format="json")
        assert first.status_code == 200

        second = APIClient().post(
            CONFIRM_URL, {"token": raw_token, "password": "another-sound-pw-2"}, format="json"
        )

        assert second.status_code in (404, 409, 410)
        user.refresh_from_db()
        assert user.check_password(STRONG_PASSWORD) is True

    def test_an_expired_token_fails(self, user):
        token, raw_token = PasswordResetToken.issue(user=user, ttl=timedelta(hours=-1))

        response = APIClient().post(
            CONFIRM_URL, {"token": raw_token, "password": STRONG_PASSWORD}, format="json"
        )

        assert response.status_code in (400, 404, 410)
        user.refresh_from_db()
        assert user.check_password("original-pw-1") is True

    def test_an_unknown_token_fails(self):
        response = APIClient().post(
            CONFIRM_URL, {"token": "not-a-real-token", "password": STRONG_PASSWORD}, format="json"
        )

        assert response.status_code == 404

    def test_a_weak_new_password_is_rejected_by_the_policy(self, user):
        """AUTH_PASSWORD_VALIDATORS must run here exactly as it does at registration."""
        token, raw_token = PasswordResetToken.issue(user=user)

        response = APIClient().post(CONFIRM_URL, {"token": raw_token, "password": "12345678"}, format="json")

        assert response.status_code == 400
        user.refresh_from_db()
        assert user.check_password("original-pw-1") is True
        # The token must still be usable -- rejecting the password must not burn it.
        assert PasswordResetToken.objects.get(pk=token.pk).is_used is False

    def test_missing_token_or_password_is_rejected_with_a_400(self, user):
        token, raw_token = PasswordResetToken.issue(user=user)

        assert APIClient().post(CONFIRM_URL, {"password": STRONG_PASSWORD}, format="json").status_code == 400
        assert APIClient().post(CONFIRM_URL, {"token": raw_token}, format="json").status_code == 400

    def test_resetting_the_password_invalidates_an_existing_session(self, user):
        """
        A reset is what someone does when they fear their account is
        compromised, so an old, already-issued access token must stop working
        immediately afterwards -- not just new logins.
        """
        client = APIClient()
        login = client.post(
            "/api/v1/auth/login/", {"username": "dash", "password": "original-pw-1"}, format="json"
        )
        assert login.status_code == 200
        old_access_cookie = login.cookies[ACCESS_COOKIE].value
        old_refresh_cookie = login.cookies[REFRESH_COOKIE].value

        # The old access token works right up until the reset.
        assert client.get("/api/v1/auth/me/").status_code == 200

        token, raw_token = PasswordResetToken.issue(user=user)
        confirm = APIClient().post(
            CONFIRM_URL, {"token": raw_token, "password": STRONG_PASSWORD}, format="json"
        )
        assert confirm.status_code == 200

        stale_client = APIClient()
        stale_client.cookies[ACCESS_COOKIE] = old_access_cookie
        assert stale_client.get("/api/v1/auth/me/").status_code == 401

        # The stale refresh token must not be able to mint a working access
        # token either: refreshing still succeeds at the JWT layer (nothing
        # here blacklists the refresh token itself), but the new access token
        # it produces carries the same stale password hash claim forward, so
        # it is rejected the same way everywhere it is actually used.
        stale_client.cookies[REFRESH_COOKIE] = old_refresh_cookie
        refreshed = stale_client.post("/api/v1/auth/refresh/")
        if refreshed.status_code == 200:
            stale_client.cookies[ACCESS_COOKIE] = refreshed.cookies[ACCESS_COOKIE].value
            assert stale_client.get("/api/v1/auth/me/").status_code == 401


@pytest.mark.django_db
class TestPasswordResetTokenModel:
    """Mirrors tenancy.models.Invitation's own token tests."""

    def test_token_is_not_stored_in_plaintext(self, user):
        token, raw_token = PasswordResetToken.issue(user=user)

        assert token.token_hash != raw_token
        assert raw_token not in token.token_hash

    def test_for_token_resolves_the_issued_token(self, user):
        token, raw_token = PasswordResetToken.issue(user=user)

        assert PasswordResetToken.for_token(raw_token) == token

    def test_for_token_rejects_an_unknown_token(self):
        assert PasswordResetToken.for_token("not-a-real-token") is None

    def test_default_expiry_is_shorter_than_an_invitations(self, user):
        from authentication.models import PASSWORD_RESET_DEFAULT_TTL
        from tenancy.models import INVITATION_DEFAULT_TTL

        assert PASSWORD_RESET_DEFAULT_TTL < INVITATION_DEFAULT_TTL


@pytest.mark.django_db
class TestAuthConfigEndpoint:
    """
    Reachable before login (AllowAny) because the person who needs to know
    whether "forgot password" will actually do anything cannot, by
    definition, have logged in yet.
    """

    def test_reports_password_reset_enabled_when_email_is_usable(self, settings):
        settings.EMAIL_USABLE = True

        response = APIClient().get(CONFIG_URL)

        assert response.status_code == 200
        assert response.data["password_reset_enabled"] is True

    def test_reports_password_reset_disabled_when_email_is_not_usable(self, settings):
        settings.EMAIL_USABLE = False

        response = APIClient().get(CONFIG_URL)

        assert response.status_code == 200
        assert response.data["password_reset_enabled"] is False
