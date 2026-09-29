"""
Integration tests for `telemetry.payload.build_payload` and the
`telemetry --show` management command.

The key-set test is the contract: schema v1 is spelled out here, independently
of the builder, so any field added to the payload without updating this test
(and docs/telemetry.md) fails the suite. The privacy test seeds recognizable
customer strings and asserts none of them leave the install.
"""
import io
import json
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import DatabaseError
from django.utils import timezone

from core_flags.models import FlagOverride, FlagType, StrategyRule, Variant
from sdk_api.models import EvaluationLog, SDKRegistration, SDKType
from telemetry import payload as payload_module
from telemetry.models import InstallationIdentity
from telemetry.payload import build_payload

SCHEMA_V1_KEYS = {
    "schema_version",
    "installation_id",
    "sent_at",
    "first_seen_at",
    "flagward_version",
    "mode",
    "server",
    "runtime",
    "runtime.python",
    "runtime.django",
    "runtime.deployment",
    "runtime.database",
    "runtime.redis_enabled",
    "runtime.email_configured",
    "runtime.default_plan",
    "usage",
    "usage.organizations",
    "usage.projects",
    "usage.environments",
    "usage.users",
    "usage.flags",
    "usage.flags.total",
    "usage.flags.boolean",
    "usage.flags.multivariate",
    "usage.flags_with_rules",
    "usage.strategy_rules",
    "usage.rules_with_rollout",
    "usage.variants",
    "usage.active_overrides",
    "sdks",
    "sdks[].type",
    "sdks[].version",
    "sdks[].active_7d",
    "evaluations_24h_bucket",
}


def flatten_keys(value, prefix=""):
    keys = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            keys.add(path)
            keys |= flatten_keys(child, path)
    elif isinstance(value, list):
        for item in value:
            keys |= flatten_keys(item, f"{prefix}[]")
    return keys


@pytest.fixture
def identity():
    return InstallationIdentity.get_or_create_singleton()


@pytest.fixture
def populated(organization, project, environment, make_flag, user):
    """An install with every kind of row the payload counts."""
    boolean = make_flag(environment=environment, key="secret-launch", name="Secret Launch")
    multivariate = make_flag(
        environment=environment, key="pricing-test", name="Pricing Test", flag_type=FlagType.MULTIVARIATE
    )
    control = Variant.objects.create(flag=multivariate, name="control", percentage_allocation=50, is_control=True)
    treatment = Variant.objects.create(flag=multivariate, name="treatment-x", percentage_allocation=50)
    StrategyRule.objects.create(flag=boolean, priority=0)
    StrategyRule.objects.create(flag=multivariate, priority=0, rollout_variant=treatment, rollout_percentage=10)
    StrategyRule.objects.create(flag=multivariate, priority=1, rollout_variant=control, rollout_percentage=100)
    FlagOverride.objects.create(flag=boolean, is_enabled=True, reason="incident at Acme")
    FlagOverride.objects.create(flag=boolean, is_enabled=False, reason="old", cleared_at=timezone.now())
    get_user_model().objects.create_user(username="ana", email="ana@acme.com", password="secret")
    get_user_model().objects.create_user(username="gone", email="gone@acme.com", password="secret", is_active=False)
    return {"boolean": boolean, "multivariate": multivariate}


@pytest.mark.django_db
class TestSchema:
    def test_the_key_set_is_exactly_schema_v1(self, identity, populated, environment):
        SDKRegistration.objects.create(environment=environment, sdk_type=SDKType.REACT, version="0.4.0")

        payload = build_payload(identity)

        assert flatten_keys(payload) == SCHEMA_V1_KEYS

    def test_the_payload_is_json_serializable(self, identity, populated):
        json.dumps(build_payload(identity))

    def test_identity_fields(self, identity):
        payload = build_payload(identity)

        assert payload["schema_version"] == 1
        assert payload["installation_id"] == str(identity.installation_id)
        assert payload["first_seen_at"] == identity.first_seen_at.isoformat()


@pytest.mark.django_db
class TestPrivacy:
    def test_no_customer_string_leaves_the_install(self, identity, populated, environment):
        SDKRegistration.objects.create(environment=environment, sdk_type="my-internal-thing", version="build-acme-42")

        serialized = json.dumps(build_payload(identity)).lower()

        for secret in [
            "secret-launch",
            "secret launch",
            "pricing-test",
            "treatment-x",
            "acme",
            "ana@acme.com",
            "dash@example.com",
            "incident",
            environment.api_key.lower(),
            "my-internal-thing",
            "build-acme-42",
        ]:
            assert secret not in serialized, secret


@pytest.mark.django_db
class TestModeAndServer:
    @pytest.mark.parametrize(("debug", "mode"), [(True, "development"), (False, "production")])
    def test_mode_follows_debug(self, settings, identity, debug, mode):
        settings.DEBUG = debug

        assert build_payload(identity)["mode"] == mode

    @pytest.mark.parametrize("server", ["asgi", "wsgi", "runserver"])
    def test_server_is_reported_as_given(self, identity, server):
        assert build_payload(identity, server=server)["server"] == server

    def test_server_defaults_to_unknown(self, identity):
        assert build_payload(identity)["server"] == "unknown"


@pytest.mark.django_db
class TestUsage:
    def test_counts(self, identity, populated):
        usage = build_payload(identity)["usage"]

        assert usage == {
            "organizations": 1,
            "projects": 1,
            "environments": 1,
            "users": 2,  # dash + ana; the inactive user is not counted
            "flags": {"total": 2, "boolean": 1, "multivariate": 1},
            "flags_with_rules": 2,
            "strategy_rules": 3,
            "rules_with_rollout": 2,
            "variants": 2,
            "active_overrides": 1,
        }

    def test_an_empty_install_reports_zeros(self, identity):
        usage = build_payload(identity)["usage"]

        assert usage["organizations"] == 0
        assert usage["flags"] == {"total": 0, "boolean": 0, "multivariate": 0}
        assert build_payload(identity)["sdks"] == []
        assert build_payload(identity)["evaluations_24h_bucket"] == "0"


@pytest.mark.django_db
class TestSdks:
    def test_sdks_are_aggregated_by_type_and_version(self, identity, project, make_environment):
        staging = make_environment(project=project, key="staging", name="Staging")
        prod = make_environment(project=project, key="prod", name="Production")
        dev = make_environment(project=project, key="dev", name="Dev")
        for env in (staging, prod):
            SDKRegistration.objects.create(environment=env, sdk_type=SDKType.REACT, version="0.4.0")
        SDKRegistration.objects.create(environment=dev, sdk_type=SDKType.REACT, version="0.3.0")
        SDKRegistration.objects.create(environment=dev, sdk_type="my-internal-thing", version="build-acme-42")

        sdks = build_payload(identity)["sdks"]

        assert sdks == [
            {"type": "other", "version": "unknown", "active_7d": 1},
            {"type": "react", "version": "0.3.0", "active_7d": 1},
            {"type": "react", "version": "0.4.0", "active_7d": 2},
        ]

    def test_only_sdks_seen_in_the_last_7_days_are_counted(self, identity, project, make_environment):
        recent = make_environment(project=project, key="recent", name="Recent")
        stale = make_environment(project=project, key="stale", name="Stale")
        SDKRegistration.objects.create(environment=recent, sdk_type=SDKType.VUE, version="0.3.0")
        old = SDKRegistration.objects.create(environment=stale, sdk_type=SDKType.VUE, version="0.3.0")
        now = timezone.now()
        SDKRegistration.objects.filter(environment=recent).update(last_seen_at=now - timedelta(days=2))
        SDKRegistration.objects.filter(pk=old.pk).update(last_seen_at=now - timedelta(days=10))

        sdks = build_payload(identity, now=now)["sdks"]

        assert sdks == [{"type": "vue", "version": "0.3.0", "active_7d": 1}]


@pytest.mark.django_db
class TestEvaluations:
    def test_only_the_last_24_hours_are_bucketed(self, identity, flag):
        now = timezone.now()
        EvaluationLog.objects.bulk_create(
            [EvaluationLog(flag=flag, context_hash="h", result="true") for _ in range(150)]
        )
        old = EvaluationLog.objects.create(flag=flag, context_hash="h", result="true")
        EvaluationLog.objects.filter(pk=old.pk).update(timestamp=now - timedelta(hours=25))

        assert build_payload(identity, now=now)["evaluations_24h_bucket"] == "100-1k"


@pytest.mark.django_db
class TestRuntime:
    def test_runtime_block(self, settings, identity, monkeypatch, tmp_path):
        settings.EMAIL_HOST = "smtp.acme.com"
        settings.DEFAULT_ORGANIZATION_PLAN = "COMMUNITY"
        dockerenv = tmp_path / ".dockerenv"
        dockerenv.touch()
        monkeypatch.setattr(payload_module, "DOCKERENV", str(dockerenv))

        runtime = build_payload(identity)["runtime"]

        assert runtime["deployment"] == "docker"
        assert runtime["database"] in {"sqlite", "postgresql"}
        assert runtime["email_configured"] is True
        assert runtime["default_plan"] == "COMMUNITY"
        assert runtime["python"].count(".") == 1
        assert runtime["django"].count(".") == 1

    def test_bare_metal_and_no_email(self, settings, identity, monkeypatch, tmp_path):
        settings.EMAIL_HOST = None
        monkeypatch.setattr(payload_module, "DOCKERENV", str(tmp_path / "missing"))

        runtime = build_payload(identity)["runtime"]

        assert runtime["deployment"] == "bare"
        assert runtime["email_configured"] is False

    @pytest.mark.parametrize(
        ("backend", "expected"),
        [
            ("django.core.cache.backends.redis.RedisCache", True),
            ("django.core.cache.backends.locmem.LocMemCache", False),
        ],
    )
    def test_redis_is_detected_from_the_cache_backend(self, settings, identity, backend, expected):
        settings.CACHES = {"default": {"BACKEND": backend}}

        assert build_payload(identity)["runtime"]["redis_enabled"] is expected

    def test_an_unknown_default_plan_is_other(self, settings, identity):
        settings.DEFAULT_ORGANIZATION_PLAN = "ACME-DEAL"

        assert build_payload(identity)["runtime"]["default_plan"] == "other"


@pytest.mark.django_db
class TestShowCommand:
    @pytest.fixture(autouse=True)
    def _no_network(self, monkeypatch):
        def refuse(*args, **kwargs):
            raise AssertionError("--show must never reach the network")

        monkeypatch.setattr("urllib.request.urlopen", refuse)

    def test_prints_the_payload_as_json(self, populated):
        out = io.StringIO()

        call_command("telemetry", "--show", stdout=out)

        printed = json.loads(out.getvalue())
        assert flatten_keys(printed) >= SCHEMA_V1_KEYS - {"sdks[].type", "sdks[].version", "sdks[].active_7d"}
        assert printed["server"] == "unknown"

    def test_uses_the_persisted_identity_when_it_exists(self, identity):
        out = io.StringIO()

        call_command("telemetry", "--show", stdout=out)

        assert json.loads(out.getvalue())["installation_id"] == str(identity.installation_id)

    def test_never_creates_the_identity(self):
        """With telemetry off, previewing must not leave a row behind."""
        out = io.StringIO()

        call_command("telemetry", "--show", stdout=out)

        assert InstallationIdentity.objects.count() == 0
        uuid.UUID(json.loads(out.getvalue())["installation_id"])

    def test_works_before_the_telemetry_migration_runs(self, monkeypatch):
        """An operator may preview right after upgrading, before `migrate`."""

        def missing_table(*args, **kwargs):
            raise DatabaseError("no such table: telemetry_installationidentity")

        monkeypatch.setattr(InstallationIdentity.objects, "filter", missing_table)
        out, err = io.StringIO(), io.StringIO()

        call_command("telemetry", "--show", stdout=out, stderr=err)

        uuid.UUID(json.loads(out.getvalue())["installation_id"])
        assert "migrate" in err.getvalue()

    def test_an_unmigrated_database_fails_with_a_clear_message(self, monkeypatch):
        def stale_schema(*args, **kwargs):
            raise DatabaseError("no such column: core_flags_strategyrule.rollout_variant_id")

        monkeypatch.setattr("telemetry.management.commands.telemetry.build_payload", stale_schema)

        with pytest.raises(CommandError, match="migrate"):
            call_command("telemetry", "--show", stdout=io.StringIO())
