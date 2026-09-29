"""
Integration tests for sending: the HTTP sender, the daily send slot, the
background loop's entry point and `telemetry --send`.

No test here touches the network. Every send goes through an injected
transport that records what it was given.
"""
import io
import json
import logging
import urllib.error
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import DatabaseError
from django.utils import timezone

from telemetry import runtime
from telemetry.models import InstallationIdentity
from telemetry.sender import post, send


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RecordingTransport:
    def __init__(self, status=204, error=None):
        self.status = status
        self.error = error
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return FakeResponse(self.status)

    @property
    def payloads(self):
        return [json.loads(request.data) for request, _ in self.requests]


@pytest.fixture
def telemetry_on(settings):
    settings.FLAGWARD_TELEMETRY = "true"
    settings.FLAGWARD_TELEMETRY_URL = "http://collector.test/v1/heartbeat"


@pytest.fixture
def transport():
    return RecordingTransport()


@pytest.fixture
def telemetry_log(caplog):
    """The telemetry logger does not propagate, so caplog is attached to it directly."""
    logger = logging.getLogger("telemetry")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger="telemetry")
    yield caplog
    logger.removeHandler(caplog.handler)


@pytest.fixture(autouse=True)
def _reset_started():
    runtime._started = False
    yield
    runtime._started = False


class TestSender:
    def test_posts_json_with_headers_and_timeout(self, settings, transport):
        settings.FLAGWARD_TELEMETRY_URL = "http://collector.test/v1/heartbeat"

        status = post({"schema_version": 1}, transport=transport)

        request, timeout = transport.requests[0]
        assert status == 204
        assert timeout == 3
        assert request.full_url == "http://collector.test/v1/heartbeat"
        assert request.get_method() == "POST"
        assert request.get_header("Content-type") == "application/json"
        assert request.get_header("User-agent").startswith("flagward-telemetry/")
        assert json.loads(request.data) == {"schema_version": 1}

    @pytest.mark.parametrize(
        "error",
        [
            urllib.error.URLError("unreachable"),
            TimeoutError("timed out"),
            urllib.error.HTTPError("http://collector.test", 500, "boom", None, None),
            ValueError("anything else"),
        ],
    )
    def test_send_swallows_every_failure_and_logs_at_debug(self, error, telemetry_log):
        status = send({"schema_version": 1}, transport=RecordingTransport(error=error))

        assert status is None
        assert telemetry_log.records
        assert all(record.levelno == logging.DEBUG for record in telemetry_log.records)

    def test_post_raises_so_the_command_can_report_it(self):
        with pytest.raises(urllib.error.URLError):
            post({}, transport=RecordingTransport(error=urllib.error.URLError("unreachable")))


@pytest.mark.django_db
class TestClaimSlot:
    def test_the_first_claim_wins_and_stamps_the_slot(self):
        now = timezone.now()

        assert runtime.claim_slot(now) is True
        assert InstallationIdentity.get_or_create_singleton().last_sent_at == now

    def test_a_second_claim_inside_the_window_loses(self):
        now = timezone.now()
        runtime.claim_slot(now)

        assert runtime.claim_slot(now + timedelta(hours=3)) is False

    def test_a_claim_after_the_window_wins_again(self):
        now = timezone.now()
        runtime.claim_slot(now)

        assert runtime.claim_slot(now + timedelta(hours=24, seconds=1)) is True

    def test_only_one_of_many_workers_wins(self):
        now = timezone.now()

        results = [runtime.claim_slot(now) for _ in range(4)]

        assert results.count(True) == 1


@pytest.mark.django_db
class TestRunOnce:
    def test_sends_the_payload_when_the_slot_is_won(self, telemetry_on, transport):
        assert runtime.run_once("asgi", transport=transport) is True

        [payload] = transport.payloads
        identity = InstallationIdentity.get_or_create_singleton()
        assert payload["installation_id"] == str(identity.installation_id)
        assert payload["server"] == "asgi"

    def test_does_not_send_when_the_slot_is_lost(self, telemetry_on, transport):
        runtime.run_once("asgi", transport=transport)

        assert runtime.run_once("asgi", transport=transport) is False
        assert len(transport.requests) == 1

    def test_a_failed_send_keeps_the_slot_claimed(self, telemetry_on):
        failing = RecordingTransport(error=urllib.error.URLError("unreachable"))

        runtime.run_once("asgi", transport=failing)
        retry = RecordingTransport()

        assert runtime.run_once("asgi", transport=retry) is False
        assert retry.requests == []

    def test_a_missing_table_is_skipped_silently(self, telemetry_on, transport, monkeypatch):
        def missing_table(*args, **kwargs):
            raise DatabaseError("no such table: telemetry_installationidentity")

        monkeypatch.setattr(runtime, "claim_slot", missing_table)

        assert runtime.run_once("asgi", transport=transport) is False
        assert transport.requests == []

    def test_any_other_error_never_propagates(self, telemetry_on, transport, monkeypatch, telemetry_log):
        def broken(*args, **kwargs):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(runtime, "build_payload", broken)

        assert runtime.run_once("asgi", transport=transport) is False
        assert all(record.levelno == logging.DEBUG for record in telemetry_log.records)

    def test_does_nothing_when_disabled(self, transport):
        assert runtime.run_once("asgi", transport=transport) is False
        assert transport.requests == []
        assert InstallationIdentity.objects.count() == 0


class FakeThread:
    created = []

    def __init__(self, target, args, daemon, name):
        self.target, self.args, self.daemon, self.name = target, args, daemon, name
        self.started = False
        FakeThread.created.append(self)

    def start(self):
        self.started = True


@pytest.fixture
def fake_thread():
    FakeThread.created = []
    return FakeThread


@pytest.mark.django_db
class TestStart:
    def test_disabled_starts_nothing_and_logs_nothing(self, fake_thread, telemetry_log):
        assert runtime.start("asgi", thread_factory=fake_thread) is None
        assert fake_thread.created == []
        assert InstallationIdentity.objects.count() == 0
        assert telemetry_log.records == []

    def test_enabled_starts_one_daemon_thread_and_announces_it(self, telemetry_on, fake_thread, telemetry_log):
        thread = runtime.start("asgi", thread_factory=fake_thread)

        assert thread.started and thread.daemon
        assert thread.args == ("asgi",)
        [notice] = [record for record in telemetry_log.records if record.levelno == logging.INFO]
        assert "FLAGWARD_TELEMETRY=false" in notice.getMessage()

    def test_starting_twice_in_one_process_is_a_no_op(self, telemetry_on, fake_thread):
        runtime.start("asgi", thread_factory=fake_thread)

        assert runtime.start("asgi", thread_factory=fake_thread) is None
        assert len(fake_thread.created) == 1

    def test_starting_touches_no_database(self, telemetry_on, fake_thread):
        """The thread does the work; the entrypoint import must stay cheap and DB-free."""
        runtime.start("asgi", thread_factory=fake_thread)

        assert InstallationIdentity.objects.count() == 0


class TestLoop:
    def test_waits_a_jitter_then_checks_every_hour(self, monkeypatch):
        sleeps, runs = [], []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 3:
                raise StopIteration

        monkeypatch.setattr(runtime, "run_once", lambda server: runs.append(server))
        monkeypatch.setattr(runtime, "close_old_connections", lambda: None)

        with pytest.raises(StopIteration):
            runtime._loop("asgi", sleep=fake_sleep)

        assert 30 <= sleeps[0] <= 300
        assert sleeps[1:] == [3600, 3600]
        assert runs == ["asgi", "asgi"]


class TestServerName:
    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["manage.py", "runserver", "0.0.0.0:8000"], "runserver"),
            (["gunicorn", "config.wsgi:application"], "wsgi"),
        ],
    )
    def test_wsgi_entrypoint_tells_runserver_apart(self, argv, expected):
        assert runtime.wsgi_server_name(argv) == expected


@pytest.mark.django_db
class TestSendCommand:
    def test_respects_the_kill_switch(self, transport, monkeypatch):
        monkeypatch.setattr("telemetry.sender.urlopen", transport)
        out = io.StringIO()

        call_command("telemetry", "--send", stdout=out)

        assert transport.requests == []
        assert "disabled" in out.getvalue()
        assert InstallationIdentity.objects.count() == 0

    def test_sends_now_ignoring_the_window(self, telemetry_on, transport, monkeypatch):
        monkeypatch.setattr("telemetry.sender.urlopen", transport)
        runtime.claim_slot(timezone.now())
        out = io.StringIO()

        call_command("telemetry", "--send", stdout=out)

        assert len(transport.requests) == 1
        assert "204" in out.getvalue()
        assert transport.payloads[0]["server"] == "unknown"

    def test_updates_the_slot(self, telemetry_on, transport, monkeypatch):
        monkeypatch.setattr("telemetry.sender.urlopen", transport)
        before = timezone.now()

        call_command("telemetry", "--send", stdout=io.StringIO())

        assert InstallationIdentity.get_or_create_singleton().last_sent_at >= before

    def test_prints_the_error_when_the_collector_is_unreachable(self, telemetry_on, monkeypatch):
        monkeypatch.setattr(
            "telemetry.sender.urlopen", RecordingTransport(error=urllib.error.URLError("connection refused"))
        )
        out, err = io.StringIO(), io.StringIO()

        call_command("telemetry", "--send", stdout=out, stderr=err)

        assert "connection refused" in err.getvalue()
