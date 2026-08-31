"""
Tests for the analytics aggregation API.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.services import SDK_ACTIVE_WINDOW
from core_flags.models import Environment, FeatureFlag, FlagOverride
from sdk_api.models import EvaluationLog, SDKRegistration, SDKType
from tenancy.models import OrganizationRole, ProjectRole


@pytest.fixture
def client(project, grant):
    """
    Authenticated API client, granted project-level analytics visibility.

    Project-level grants cascade to every environment under `project`
    (`tenancy.scoping.environments_with`), so any environment the rest of
    this file creates via the `project`/`environment` fixtures stays visible
    to this client without needing a per-environment grant.
    """
    api_client = APIClient()
    user = get_user_model().objects.create_user(username="dash", email="dash@example.com", password="secret")
    grant(user, org=project.organization, role=OrganizationRole.USER)
    grant(user, project=project, role=ProjectRole.VIEWER)
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def environment(project):
    return Environment.objects.create(name="Production", key="prod", project=project)


def _log_at(flag, result, moment, context_hash="a"):
    """Create an evaluation log at an exact instant (timestamp is auto_now_add)."""
    log = EvaluationLog.objects.create(
        flag=flag, context_hash=context_hash, result=result
    )
    EvaluationLog.objects.filter(id=log.id).update(timestamp=moment)
    return log


@pytest.mark.django_db
class TestOverview:
    """Tests for /api/v1/analytics/overview/."""

    def test_counts_flags_sdks_evaluations_and_overrides(self, client, environment):
        enabled = FeatureFlag.objects.create(
            environment=environment, key="on", name="On", is_enabled=True
        )
        FeatureFlag.objects.create(
            environment=environment, key="off", name="Off", is_enabled=False
        )
        SDKRegistration.objects.create(
            environment=environment, sdk_type=SDKType.PYTHON, version="1.0.0"
        )
        _log_at(enabled, True, timezone.now() - timedelta(minutes=5))
        _log_at(enabled, False, timezone.now() - timedelta(minutes=6), context_hash="b")
        FlagOverride.objects.create(flag=enabled, is_enabled=True, reason="rollback")

        response = client.get("/api/v1/analytics/overview/")

        assert response.status_code == 200
        body = response.data
        assert body["environments"]["total"] == 1
        assert body["flags"]["total"] == 2
        assert body["flags"]["enabled"] == 1
        assert body["flags"]["disabled"] == 1
        assert body["sdks"]["total"] == 1
        assert body["sdks"]["active"] == 1
        assert body["evaluations"]["total"] == 2
        assert body["evaluations"]["last_24h"] == 2
        assert body["evaluations"]["true_rate"] == 0.5
        assert body["overrides"]["total"] == 1
        assert body["overrides"]["last_24h"] == 1

    def test_true_rate_is_null_without_evaluations(self, client, environment):
        response = client.get("/api/v1/analytics/overview/")

        assert response.status_code == 200
        assert response.data["evaluations"]["true_rate"] is None

    def test_marks_sdk_stale_past_the_active_window(self, client, environment):
        registration = SDKRegistration.objects.create(
            environment=environment, sdk_type=SDKType.PYTHON, version="1.0.0"
        )
        SDKRegistration.objects.filter(id=registration.id).update(
            last_seen_at=timezone.now() - SDK_ACTIVE_WINDOW - timedelta(minutes=1)
        )

        response = client.get("/api/v1/analytics/overview/")

        assert response.data["sdks"]["active"] == 0
        assert response.data["sdks"]["stale"] == 1

    def test_scopes_to_one_environment(self, client, environment, project):
        other = Environment.objects.create(name="Staging", key="staging", project=project)
        FeatureFlag.objects.create(environment=environment, key="a", name="A")
        FeatureFlag.objects.create(environment=other, key="b", name="B")

        response = client.get(f"/api/v1/analytics/overview/?environment={other.id}")

        assert response.data["flags"]["total"] == 1
        assert response.data["environments"]["total"] == 1

    def test_requires_authentication(self):
        response = APIClient().get("/api/v1/analytics/overview/")

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestEvaluationsTimeseries:
    """Tests for /api/v1/analytics/evaluations/timeseries/."""

    def test_emits_one_bucket_per_hour_including_empty_ones(self, client, environment):
        flag = FeatureFlag.objects.create(environment=environment, key="a", name="A")
        _log_at(flag, True, timezone.now())

        response = client.get("/api/v1/analytics/evaluations/timeseries/?hours=6")

        assert response.status_code == 200
        assert response.data["hours"] == 6
        assert len(response.data["buckets"]) == 6
        assert response.data["total"] == 1
        assert response.data["buckets"][-1]["total"] == 1
        assert response.data["buckets"][0]["total"] == 0

    def test_splits_true_and_false(self, client, environment):
        flag = FeatureFlag.objects.create(environment=environment, key="a", name="A")
        now = timezone.now()
        _log_at(flag, True, now, context_hash="a")
        _log_at(flag, False, now, context_hash="b")

        response = client.get("/api/v1/analytics/evaluations/timeseries/?hours=1")

        bucket = response.data["buckets"][0]
        assert bucket["total"] == 2
        assert bucket["true_count"] == 1
        assert bucket["false_count"] == 1

    def test_excludes_evaluations_outside_the_window(self, client, environment):
        flag = FeatureFlag.objects.create(environment=environment, key="a", name="A")
        _log_at(flag, True, timezone.now() - timedelta(hours=10))

        response = client.get("/api/v1/analytics/evaluations/timeseries/?hours=2")

        assert response.data["total"] == 0

    def test_clamps_invalid_hours_to_the_default(self, client, environment):
        response = client.get("/api/v1/analytics/evaluations/timeseries/?hours=banana")

        assert response.status_code == 200
        assert response.data["hours"] == 24

    def test_clamps_hours_to_the_maximum(self, client, environment):
        response = client.get("/api/v1/analytics/evaluations/timeseries/?hours=99999")

        assert response.status_code == 200
        assert response.data["hours"] == 168


@pytest.mark.django_db
class TestTopFlags:
    """Tests for /api/v1/analytics/flags/top/."""

    def test_orders_by_evaluation_count(self, client, environment):
        busy = FeatureFlag.objects.create(environment=environment, key="busy", name="Busy")
        quiet = FeatureFlag.objects.create(
            environment=environment, key="quiet", name="Quiet"
        )
        now = timezone.now()
        for index in range(3):
            _log_at(busy, True, now, context_hash=f"busy-{index}")
        _log_at(quiet, False, now, context_hash="quiet-0")

        response = client.get("/api/v1/analytics/flags/top/")

        assert response.status_code == 200
        results = response.data["results"]
        assert [row["flag_key"] for row in results] == ["busy", "quiet"]
        assert results[0]["evaluations"] == 3
        assert results[0]["true_rate"] == 1.0
        assert results[1]["true_rate"] == 0.0

    def test_respects_limit(self, client, environment):
        now = timezone.now()
        for index in range(4):
            flag = FeatureFlag.objects.create(
                environment=environment, key=f"flag-{index}", name=f"Flag {index}"
            )
            _log_at(flag, True, now, context_hash=f"h-{index}")

        response = client.get("/api/v1/analytics/flags/top/?limit=2")

        assert len(response.data["results"]) == 2

    def test_returns_empty_without_traffic(self, client, environment):
        FeatureFlag.objects.create(environment=environment, key="a", name="A")

        response = client.get("/api/v1/analytics/flags/top/")

        assert response.data["results"] == []


@pytest.mark.django_db
class TestSDKHealth:
    """Tests for /api/v1/analytics/sdks/health/."""

    def test_groups_by_type_and_version(self, client, environment):
        SDKRegistration.objects.create(
            environment=environment, sdk_type=SDKType.PYTHON, version="1.0.0"
        )
        stale = SDKRegistration.objects.create(
            environment=environment, sdk_type=SDKType.GO, version="2.0.0"
        )
        SDKRegistration.objects.filter(id=stale.id).update(
            last_seen_at=timezone.now() - SDK_ACTIVE_WINDOW - timedelta(minutes=1)
        )

        response = client.get("/api/v1/analytics/sdks/health/")

        assert response.status_code == 200
        assert response.data["total"] == 2
        assert response.data["active"] == 1
        assert response.data["stale"] == 1
        by_type = {row["sdk_type"]: row for row in response.data["by_type"]}
        assert by_type["PYTHON"]["active"] == 1
        assert by_type["GO"]["stale"] == 1
        assert len(response.data["by_version"]) == 2

    def test_empty_fleet(self, client, environment):
        response = client.get("/api/v1/analytics/sdks/health/")

        assert response.data["total"] == 0
        assert response.data["by_type"] == []


@pytest.mark.django_db
class TestOverviewWithOverrides:
    """The overview must report what SDKs actually serve, not just configuration."""

    def test_counts_active_overrides(self, client, environment):
        flag = FeatureFlag.objects.create(
            environment=environment, key="a", name="A", is_enabled=True
        )
        lifted = FlagOverride.objects.create(flag=flag, is_enabled=False, reason="old")
        lifted.lift()
        FlagOverride.objects.create(flag=flag, is_enabled=False, reason="current")

        body = client.get("/api/v1/analytics/overview/").data

        assert body["overrides"]["total"] == 2
        assert body["overrides"]["active"] == 1

    def test_effective_enabled_accounts_for_overrides(self, client, environment):
        # Configured on, forced off.
        forced_off = FeatureFlag.objects.create(
            environment=environment, key="off", name="Off", is_enabled=True
        )
        FlagOverride.objects.create(flag=forced_off, is_enabled=False, reason="outage")

        # Configured off, forced on.
        forced_on = FeatureFlag.objects.create(
            environment=environment, key="on", name="On", is_enabled=False
        )
        FlagOverride.objects.create(flag=forced_on, is_enabled=True, reason="force")

        # Plain enabled flag, no override.
        FeatureFlag.objects.create(
            environment=environment, key="plain", name="Plain", is_enabled=True
        )

        body = client.get("/api/v1/analytics/overview/").data

        assert body["flags"]["total"] == 3
        assert body["flags"]["enabled"] == 2, "configured state"
        assert body["flags"]["effective_enabled"] == 2, "plain + forced_on"
        assert body["flags"]["overridden"] == 2

    def test_lifted_override_stops_counting_as_overridden(self, client, environment):
        flag = FeatureFlag.objects.create(
            environment=environment, key="a", name="A", is_enabled=True
        )
        override = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="outage"
        )
        override.lift()

        body = client.get("/api/v1/analytics/overview/").data

        assert body["flags"]["overridden"] == 0
        assert body["flags"]["effective_enabled"] == 1
        assert body["overrides"]["active"] == 0


@pytest.mark.django_db
class TestAnalyticsScoping:
    """
    Spec (access-control): Analytics Scoping Is Always Bounded.
    Design D7 test 12 / D8: `build_*` take `environments` first with no
    default, so a global aggregate cannot be expressed.
    """

    def test_no_params_scopes_to_the_users_visible_environments(
        self, user, grant, api_client, make_project, make_environment, make_flag
    ):
        visible_project = make_project(name="Visible", key="visible")
        visible_env_a = make_environment(project=visible_project, key="a")
        visible_env_b = make_environment(project=visible_project, key="b")
        hidden_project = make_project(name="Hidden", key="hidden")
        hidden_env = make_environment(project=hidden_project, key="c")

        make_flag(environment=visible_env_a, key="flag-a")
        make_flag(environment=visible_env_b, key="flag-b")
        make_flag(environment=hidden_env, key="flag-c")

        grant(user, org=visible_project.organization, role=OrganizationRole.USER)
        grant(user, project=visible_project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.get("/api/v1/analytics/overview/")

        assert response.status_code == 200
        assert response.data["environments"]["total"] == 2
        assert response.data["flags"]["total"] == 2

    def test_environment_filter_for_an_invisible_environment_returns_404(
        self, user, grant, api_client, project, make_project, make_environment
    ):
        grant(user, project=project, role=ProjectRole.VIEWER)
        foreign_project = make_project(name="Foreign", key="foreign")
        foreign_environment = make_environment(project=foreign_project, key="foreign-env")
        client = api_client(user)

        response = client.get(
            f"/api/v1/analytics/overview/?environment={foreign_environment.id}"
        )

        assert response.status_code == 404

    def test_malformed_environment_filter_returns_400_not_treated_as_absent(
        self, user, grant, api_client, project
    ):
        grant(user, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.get("/api/v1/analytics/overview/?environment=not-a-uuid")

        assert response.status_code == 400

    def test_project_filter_for_an_invisible_project_returns_404(
        self, user, grant, api_client, project, make_project
    ):
        grant(user, project=project, role=ProjectRole.VIEWER)
        foreign_project = make_project(name="Foreign", key="foreign-2")
        client = api_client(user)

        response = client.get(f"/api/v1/analytics/overview/?project={foreign_project.id}")

        assert response.status_code == 404

    def test_malformed_project_filter_returns_400_not_treated_as_absent(
        self, user, grant, api_client, project
    ):
        grant(user, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.get("/api/v1/analytics/overview/?project=not-a-uuid")

        assert response.status_code == 400

    def test_project_filter_scopes_to_the_projects_environments(
        self, user, grant, api_client, make_project, make_environment, make_flag
    ):
        target_project = make_project(name="Target", key="target")
        target_env = make_environment(project=target_project, key="a")
        make_flag(environment=target_env, key="flag-a")
        other_project = make_project(name="Other", key="other")
        other_env = make_environment(project=other_project, key="b")
        make_flag(environment=other_env, key="flag-b")

        grant(user, org=target_project.organization, role=OrganizationRole.USER)
        grant(user, project=target_project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.get(f"/api/v1/analytics/overview/?project={target_project.id}")

        assert response.status_code == 200
        assert response.data["environments"]["total"] == 1
        assert response.data["flags"]["total"] == 1

    def test_user_with_no_grants_gets_200_with_zeroed_counters(self, user, api_client):
        client = api_client(user)

        response = client.get("/api/v1/analytics/overview/")

        assert response.status_code == 200
        assert response.data["environments"]["total"] == 0
        assert response.data["flags"]["total"] == 0

    def test_environments_total_reflects_scope_not_the_global_count(
        self, user, grant, api_client, make_project, make_environment
    ):
        visible_project = make_project(name="Visible", key="visible-total")
        make_environment(project=visible_project, key="a")
        make_environment(project=visible_project, key="b")
        for index in range(3):
            hidden_project = make_project(name=f"Hidden{index}", key=f"hidden-{index}")
            make_environment(project=hidden_project, key="x")

        grant(user, org=visible_project.organization, role=OrganizationRole.USER)
        grant(user, project=visible_project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.get("/api/v1/analytics/overview/")

        assert response.data["environments"]["total"] == 2
