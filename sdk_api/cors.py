"""
CORS for the SDK surface, which runs in other people's browsers.

A customer loads @flagward/react on their own domain and calls
/api/v1/sdk/flags/ from it. This deployment has never heard of that origin and
never will, so the SDK paths answer any of them.

Nothing else does. The dashboard authenticates with an httpOnly cookie and asks
the browser to send it, so an open policy there would let any site on the
internet make authenticated requests with a logged-in user's session and read
the answer. django-cors-headers keeps its allowlist for those paths and is kept
off these ones by CORS_URLS_REGEX -- otherwise a request from an allowed origin
to an SDK path would come back with this wildcard *and* that middleware's
`Access-Control-Allow-Credentials: true`, which is the one combination worth
being afraid of.

What makes opening these paths safe is that they carry no session. The API key
arrives in a header the caller sets by hand, so no cookie rides along, and
`Access-Control-Allow-Credentials` is never sent -- a browser will not attach
one to a request whose response does not ask for it.
"""
import re

from django.http import HttpResponse

# The trailing slash matters. `/api/v1/sdk-registrations/` reads which SDKs have
# connected, authenticates with the dashboard's cookie, and shares this prefix
# by coincidence -- a looser match would open a session-authenticated endpoint.
SDK_PATHS = re.compile(r"^/api/v1/sdk/")

ALLOWED_METHODS = "GET, POST, OPTIONS"
ALLOWED_HEADERS = "Content-Type, X-API-Key"
PREFLIGHT_CACHE_SECONDS = "86400"


class SdkCorsMiddleware:
    """Answers any origin, for the SDK surface only, and never with credentials."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not SDK_PATHS.match(request.path):
            return self.get_response(request)

        if self._is_preflight(request):
            # Answered here rather than by a view: a preflight asks whether the
            # real request is allowed, and routing it would mean every SDK view
            # had to handle a method it does not implement.
            response = HttpResponse(status=200)
        else:
            response = self.get_response(request)

        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = ALLOWED_METHODS
        response["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
        response["Access-Control-Max-Age"] = PREFLIGHT_CACHE_SECONDS

        return response

    @staticmethod
    def _is_preflight(request):
        return request.method == "OPTIONS" and "HTTP_ACCESS_CONTROL_REQUEST_METHOD" in request.META
