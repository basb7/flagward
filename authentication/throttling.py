"""
Rate limiting for public, unauthenticated auth endpoints.
"""
from rest_framework.throttling import SimpleRateThrottle

from authentication.emails import normalize_email


class PasswordResetRequestThrottle(SimpleRateThrottle):
    """
    Throttles POST /api/v1/auth/password-reset/request/ by the *submitted*
    email address, not the caller's IP.

    The threat this guards against is one mailbox being flooded with reset
    emails, which an IP-keyed throttle would not stop (an attacker can send
    from many IPs, all aimed at one victim address). Keying on the address
    itself stops that directly.

    What this does NOT cover: an attacker spreading requests across many
    different target addresses from one source is not slowed down at all,
    and this throttle does nothing to equalise response timing between a
    known and an unknown address -- both are left as documented limitations,
    not silently ignored.
    """

    scope = "password_reset_request"

    def get_cache_key(self, request, view):
        email = normalize_email(str(request.data.get("email") or ""))
        if not email:
            # Nothing to throttle without a target address; the view's own
            # validation rejects a missing email regardless.
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}
