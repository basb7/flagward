"""
The single switch every telemetry code path asks before touching the database
or the network.
"""
from django.conf import settings

_TRUTHY = frozenset({"1", "true", "yes", "on"})

DEFAULT_TELEMETRY_URL = "https://telemetry.flagward.com/v1/heartbeat"


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
    """
    Empty means default: compose forwards `${FLAGWARD_TELEMETRY_URL:-}`, which
    reaches the container as an empty string rather than an unset variable.
    """
    return settings.FLAGWARD_TELEMETRY_URL or DEFAULT_TELEMETRY_URL
