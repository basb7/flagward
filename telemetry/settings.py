"""
The single switch every telemetry code path asks before touching the database
or the network.
"""
from django.conf import settings

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Fixed on purpose: operators can turn telemetry off (FLAGWARD_TELEMETRY=false)
# but not redirect it, so there is exactly one place the data can go and it is
# the one docs/telemetry.md describes.
TELEMETRY_URL = "https://telemetry.flagward.com/v1/heartbeat"


def is_enabled() -> bool:
    """
    An explicit FLAGWARD_TELEMETRY always wins. Unset or empty means on, except
    inside a CI run. A value that is neither truthy nor falsy counts as off: a
    typo must never be read as consent to send.

    DEBUG plays no part here; it only decides the reported `mode`.
    """
    raw = (settings.FLAGWARD_TELEMETRY or "").strip().lower()
    if not raw:
        return not settings.CI
    return raw in _TRUTHY


def telemetry_url() -> str:
    return TELEMETRY_URL
