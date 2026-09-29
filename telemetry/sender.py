"""
Posts a telemetry payload to the collector.

Stdlib only: the runtime requirements carry no HTTP client, and one daily POST
does not justify adding one.
"""
import json
import logging
from urllib.request import Request, urlopen

from telemetry.settings import telemetry_url
from telemetry.version import get_version

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 3


def post(payload: dict, *, transport=None) -> int:
    """Send `payload` and return the HTTP status. Raises on any failure."""
    request = Request(
        telemetry_url(),
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"flagward-telemetry/{get_version()}",
        },
    )
    with (transport or urlopen)(request, timeout=TIMEOUT_SECONDS) as response:
        return response.status


def send(payload: dict, *, transport=None) -> int | None:
    """
    `post`, but never raises. Failures are logged at DEBUG only, so an
    air-gapped install that cannot reach the collector stays quiet.
    """
    try:
        return post(payload, transport=transport)
    except Exception as error:  # noqa: BLE001 -- telemetry must never break the app
        logger.debug("Telemetry send failed: %s", error)
        return None
