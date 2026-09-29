"""
The background heartbeat: at most one send per installation per 24 hours.

`start()` is called from the server entrypoints (config/asgi.py and
config/wsgi.py), never from AppConfig.ready(), so `migrate`, the test suite and
other management commands never spawn it. Every worker process runs its own
loop; `claim_slot()` makes sure only one of them sends per window, across
workers and replicas sharing the database.
"""
import logging
import random
import threading
import time
from datetime import datetime, timedelta

from django.db import DatabaseError, close_old_connections
from django.db.models import Q
from django.utils import timezone

from telemetry.models import SINGLETON_ID, InstallationIdentity
from telemetry.payload import build_payload
from telemetry.sender import send
from telemetry.settings import is_enabled

logger = logging.getLogger(__name__)

SEND_INTERVAL = timedelta(hours=24)
CHECK_INTERVAL_SECONDS = 3600
# Spreads the collector's load after many installs restart at once, and keeps
# a crash-looping container from sending on every restart.
JITTER_SECONDS = (30, 300)

_started = False
_start_lock = threading.Lock()


def claim_slot(now: datetime | None = None) -> bool:
    """
    Atomically move `last_sent_at` forward if the window has passed. The
    conditional UPDATE is the whole dedup: only the worker whose UPDATE hits
    the row may send.
    """
    now = now or timezone.now()
    InstallationIdentity.get_or_create_singleton()
    claimed = (
        InstallationIdentity.objects.filter(id=SINGLETON_ID)
        .filter(Q(last_sent_at__isnull=True) | Q(last_sent_at__lt=now - SEND_INTERVAL))
        .update(last_sent_at=now)
    )
    return claimed == 1


def run_once(server: str, *, transport=None) -> bool:
    """
    One check: claim, build, send. Returns whether a send was attempted. The
    slot stays claimed even if the send fails -- missing a day is fine,
    retrying an unreachable collector every hour is not.
    """
    if not is_enabled():
        return False
    try:
        if not claim_slot():
            return False
        identity = InstallationIdentity.get_or_create_singleton()
        send(build_payload(identity, server=server), transport=transport)
        return True
    except DatabaseError:
        # Not migrated yet; the next check tries again.
        return False
    except Exception as error:  # noqa: BLE001 -- telemetry must never break the app
        logger.debug("Telemetry check failed: %s", error)
        return False


def _loop(server: str, *, sleep=time.sleep) -> None:
    sleep(random.uniform(*JITTER_SECONDS))
    while True:
        run_once(server)
        close_old_connections()
        sleep(CHECK_INTERVAL_SECONDS)


def start(server: str, *, thread_factory=threading.Thread):
    """
    Start this process's heartbeat thread, once. Touches no database: the
    entrypoint import must stay cheap even before `migrate` has run.
    """
    global _started
    if not is_enabled():
        return None
    with _start_lock:
        if _started:
            return None
        _started = True
    logger.info(
        "Anonymous telemetry is on. Disable it with FLAGWARD_TELEMETRY=false. "
        "See docs/telemetry.md for exactly what is sent."
    )
    thread = thread_factory(target=_loop, args=(server,), daemon=True, name="flagward-telemetry")
    thread.start()
    return thread


def wsgi_server_name(argv: list[str]) -> str:
    """`runserver` also serves through config/wsgi.py; tell it apart from a real WSGI server."""
    return "runserver" if "runserver" in argv else "wsgi"
