"""
CORS is opened for the SDK surface and for nothing else.

The SDK runs in *other people's* browsers, on domains this deployment has
never heard of: a customer's site loads @flagward/react and calls
/api/v1/sdk/flags/ from their own origin. That path has to answer any origin
or the product does not work.

Everything else must not. The dashboard authenticates with an httpOnly cookie
and asks the browser to send it (`credentials: "include"`), so an open policy
there would let any site on the internet make authenticated requests with a
logged-in user's session and read the answer -- their organizations, their
projects, their environments' API keys.

The two are safe to treat differently because they authenticate differently.
The SDK sends an API key in a header the caller sets explicitly; no cookie
rides along, so `Access-Control-Allow-Credentials` is never sent back and a
browser will not attach one.
"""
import pytest
from django.test import Client

SDK_PATH = "/api/v1/sdk/flags/"
MONITORING_PATH = "/api/v1/sdk-registrations/"
DASHBOARD_PATH = "/api/v1/tenancy/organizations/"

STRANGER = "https://a-customers-own-site.example"
KNOWN = "http://localhost:3000"


@pytest.mark.django_db
class TestTheSdkSurfaceAnswersAnyOrigin:
    def test_a_stranger_gets_an_allow_origin_header(self):
        response = Client().get(SDK_PATH, HTTP_ORIGIN=STRANGER)

        assert response["Access-Control-Allow-Origin"] == "*"

    def test_it_never_allows_credentials(self):
        """The property that makes opening this path safe. A wildcard origin
        with credentials would be refused by browsers anyway; echoing the
        origin back *with* credentials is the dangerous shape, and neither can
        happen if the header is simply never sent."""
        response = Client().get(SDK_PATH, HTTP_ORIGIN=STRANGER)

        assert "Access-Control-Allow-Credentials" not in response

    def test_a_preflight_is_answered(self):
        """The SDK sends X-API-Key, which is not a CORS-safelisted header, so
        the browser asks permission before the real request."""
        response = Client().options(
            SDK_PATH,
            HTTP_ORIGIN=STRANGER,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-api-key",
        )

        assert response.status_code == 200
        assert response["Access-Control-Allow-Origin"] == "*"
        assert "x-api-key" in response["Access-Control-Allow-Headers"].lower()

    def test_a_configured_origin_gets_the_wildcard_and_nothing_else(self):
        """The case CORS_URLS_REGEX exists for, and the one a stranger-only
        test never reaches.

        django-cors-headers answers an origin on its allowlist with that
        origin and `Access-Control-Allow-Credentials: true`. On an SDK path
        this middleware then overwrites the origin with `*`, and the pair that
        comes out -- a wildcard *with* credentials -- is refused by every
        browser. The dashboard's own origin would be unable to call the SDK
        API, which is a functional break rather than a security one, and an
        invisible one: the headers look present.

        Keeping django-cors-headers off these paths is what prevents it.
        """
        response = Client().get(SDK_PATH, HTTP_ORIGIN=KNOWN)

        assert response["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Credentials" not in response

    def test_the_stream_is_reachable_too(self):
        """EventSource is a cross-origin request like any other, and live
        updates are half the product."""
        response = Client().get("/api/v1/sdk/stream/", HTTP_ORIGIN=STRANGER)

        assert response["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
class TestNothingElseIsOpened:
    def test_the_dashboard_refuses_a_stranger(self):
        response = Client().get(DASHBOARD_PATH, HTTP_ORIGIN=STRANGER)

        assert "Access-Control-Allow-Origin" not in response

    def test_the_dashboard_still_answers_a_configured_origin(self):
        response = Client().get(DASHBOARD_PATH, HTTP_ORIGIN=KNOWN)

        assert response["Access-Control-Allow-Origin"] == KNOWN
        assert response["Access-Control-Allow-Credentials"] == "true"

    def test_the_monitoring_endpoint_is_not_the_sdk(self):
        """`/api/v1/sdk-registrations/` reads which SDKs have connected. It
        shares a prefix with the SDK surface and nothing else: it authenticates
        with the dashboard's cookie, and a path match loose enough to catch it
        would open a session-authenticated endpoint to every origin."""
        response = Client().get(MONITORING_PATH, HTTP_ORIGIN=STRANGER)

        assert "Access-Control-Allow-Origin" not in response
