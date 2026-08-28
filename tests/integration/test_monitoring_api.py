"""
Tests for the dashboard-facing monitoring API: SDK registrations,
evaluation logs and flag overrides.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core_flags.models import Environment, FeatureFlag, FlagOverride
from sdk_api.models import EvaluationLog, SDKRegistration, SDKType


@pytest.fixture
def client():
    """Authenticated API client, as a dashboard user would be."""
    api_client = APIClient()
    user = get_user_model().objects.create_user(username="dash", password="secret")
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def environments():
    """Two environments, so scoping filters can be proven to actually scope."""
    return {
        "prod": Environment.objects.create(name="Production", key="prod"),
        "staging": Environment.objects.create(name="Staging", key="staging"),
    }


@pytest.mark.django_db
class TestSDKRegistrationViewSet:
    """Tests for /api/v1/sdk-registrations/."""

    def test_list_returns_registrations(self, client, environments):
        SDKRegistration.objects.create(
            environment=environments["prod"], sdk_type=SDKType.PYTHON, version="1.0.0"
        )

        response = client.get("/api/v1/sdk-registrations/")

        assert response.status_code == 200
        assert response.data["count"] == 1
        row = response.data["results"][0]
        assert row["sdk_type"] == "PYTHON"
        assert row["version"] == "1.0.0"
        assert row["environment_key"] == "prod"

    def test_list_filters_by_environment(self, client, environments):
        SDKRegistration.objects.create(
            environment=environments["prod"], sdk_type=SDKType.PYTHON, version="1.0.0"
        )
        SDKRegistration.objects.create(
            environment=environments["staging"], sdk_type=SDKType.GO, version="2.0.0"
        )

        response = client.get(
            f"/api/v1/sdk-registrations/?environment={environments['prod'].id}"
        )

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["environment_key"] == "prod"

    def test_malformed_filter_returns_400_not_an_empty_page(self, client, environments):
        SDKRegistration.objects.create(
            environment=environments["prod"], sdk_type=SDKType.PYTHON, version="1.0.0"
        )

        response = client.get("/api/v1/sdk-registrations/?environment=not-a-uuid")

        assert response.status_code == 400

    def test_is_read_only(self, client, environments):
        response = client.post(
            "/api/v1/sdk-registrations/",
            {
                "environment": str(environments["prod"].id),
                "sdk_type": "PYTHON",
                "version": "1.0.0",
            },
            format="json",
        )

        assert response.status_code == 405

    def test_requires_authentication(self, environments):
        response = APIClient().get("/api/v1/sdk-registrations/")

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestEvaluationLogViewSet:
    """Tests for /api/v1/evaluations/."""

    def test_list_returns_newest_first(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        older = EvaluationLog.objects.create(flag=flag, context_hash="a", result=False)
        EvaluationLog.objects.filter(id=older.id).update(
            timestamp=timezone.now() - timedelta(hours=1)
        )
        EvaluationLog.objects.create(flag=flag, context_hash="b", result=True)

        response = client.get("/api/v1/evaluations/")

        assert response.status_code == 200
        assert response.data["count"] == 2
        assert response.data["results"][0]["context_hash"] == "b"
        assert response.data["results"][0]["flag_key"] == "checkout"

    def test_filters_by_flag(self, client, environments):
        kept = FeatureFlag.objects.create(
            environment=environments["prod"], key="kept", name="Kept"
        )
        other = FeatureFlag.objects.create(
            environment=environments["prod"], key="other", name="Other"
        )
        EvaluationLog.objects.create(flag=kept, context_hash="a", result=True)
        EvaluationLog.objects.create(flag=other, context_hash="b", result=True)

        response = client.get(f"/api/v1/evaluations/?flag={kept.id}")

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["flag_key"] == "kept"

    def test_filters_by_result(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        EvaluationLog.objects.create(flag=flag, context_hash="a", result=True)
        EvaluationLog.objects.create(flag=flag, context_hash="b", result=False)

        response = client.get("/api/v1/evaluations/?result=false")

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["result"] is False

    def test_filters_by_environment(self, client, environments):
        prod_flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        staging_flag = FeatureFlag.objects.create(
            environment=environments["staging"], key="checkout", name="Checkout"
        )
        EvaluationLog.objects.create(flag=prod_flag, context_hash="a", result=True)
        EvaluationLog.objects.create(flag=staging_flag, context_hash="b", result=True)

        response = client.get(
            f"/api/v1/evaluations/?environment={environments['prod'].id}"
        )

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["environment_key"] == "prod"


@pytest.mark.django_db
class TestFlagOverrideViewSet:
    """Tests for /api/v1/overrides/."""

    def test_create_forces_the_flag_without_rewriting_its_configuration(
        self, client, environments
    ):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"],
            key="checkout",
            name="Checkout",
            is_enabled=True,
        )

        response = client.post(
            "/api/v1/overrides/",
            {"flag": str(flag.id), "is_enabled": False, "reason": "Payment outage"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["reason"] == "Payment outage"
        assert response.data["flag_key"] == "checkout"
        assert response.data["is_active"] is True
        assert response.data["cleared_at"] is None

        # The configured state is untouched; only the effective value changes.
        flag.refresh_from_db()
        assert flag.is_enabled is True

        flag_payload = client.get(f"/api/v1/flags/{flag.id}/").data
        assert flag_payload["is_enabled"] is True
        assert flag_payload["effective_is_enabled"] is False
        assert flag_payload["active_override"]["reason"] == "Payment outage"

    def test_a_new_override_lifts_the_previous_active_one(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        first = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="first"
        )

        client.post(
            "/api/v1/overrides/",
            {"flag": str(flag.id), "is_enabled": True, "reason": "second"},
            format="json",
        )

        first.refresh_from_db()
        assert first.is_active is False
        assert FlagOverride.objects.active().count() == 1
        assert FlagOverride.objects.active_for(flag).reason == "second"

    def test_a_new_override_leaves_another_flags_override_alone(
        self, client, environments
    ):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        other = FeatureFlag.objects.create(
            environment=environments["prod"], key="search", name="Search"
        )
        untouched = FlagOverride.objects.create(
            flag=other, is_enabled=False, reason="other flag"
        )

        client.post(
            "/api/v1/overrides/",
            {"flag": str(flag.id), "is_enabled": False, "reason": "this flag"},
            format="json",
        )

        untouched.refresh_from_db()
        assert untouched.is_active is True

    def test_lift_stops_forcing_the_flag_and_keeps_the_row(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"],
            key="checkout",
            name="Checkout",
            is_enabled=True,
        )
        override = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="Payment outage"
        )

        response = client.post(f"/api/v1/overrides/{override.id}/lift/")

        assert response.status_code == 200
        assert response.data["is_active"] is False
        assert response.data["cleared_at"] is not None
        assert FlagOverride.objects.count() == 1, "the trail must survive a lift"

        flag_payload = client.get(f"/api/v1/flags/{flag.id}/").data
        assert flag_payload["effective_is_enabled"] is True
        assert flag_payload["active_override"] is None

    def test_lift_is_idempotent_over_http(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        override = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="outage"
        )

        first = client.post(f"/api/v1/overrides/{override.id}/lift/")
        second = client.post(f"/api/v1/overrides/{override.id}/lift/")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.data["cleared_at"] == second.data["cleared_at"]

    def test_filters_by_active(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        lifted = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="lifted"
        )
        lifted.lift()
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="still on")

        active = client.get("/api/v1/overrides/?active=true")
        inactive = client.get("/api/v1/overrides/?active=false")

        assert [row["reason"] for row in active.data["results"]] == ["still on"]
        assert [row["reason"] for row in inactive.data["results"]] == ["lifted"]

    def test_list_returns_newest_first(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        first = FlagOverride.objects.create(flag=flag, is_enabled=False, reason="first")
        FlagOverride.objects.filter(id=first.id).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="second")

        response = client.get("/api/v1/overrides/")

        assert response.status_code == 200
        assert [row["reason"] for row in response.data["results"]] == ["second", "first"]

    def test_is_append_only(self, client, environments):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        override = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="Payment outage"
        )

        patch = client.patch(
            f"/api/v1/overrides/{override.id}/", {"reason": "rewritten"}, format="json"
        )
        delete = client.delete(f"/api/v1/overrides/{override.id}/")

        assert patch.status_code == 405
        assert delete.status_code == 405


@pytest.mark.django_db
class TestQueryParamFilterMixin:
    """Cross-cutting behaviour of the shared filter mixin."""

    @pytest.mark.parametrize("raw,expected_result", [("false", False), ("0", False), ("true", True), ("1", True)])
    def test_accepts_common_boolean_literals(self, client, environments, raw, expected_result):
        flag = FeatureFlag.objects.create(
            environment=environments["prod"], key="checkout", name="Checkout"
        )
        EvaluationLog.objects.create(flag=flag, context_hash="a", result=True)
        EvaluationLog.objects.create(flag=flag, context_hash="b", result=False)

        response = client.get(f"/api/v1/evaluations/?result={raw}")

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["result"] is expected_result

    def test_rejects_a_non_boolean_value(self, client, environments):
        response = client.get("/api/v1/evaluations/?result=banana")

        assert response.status_code == 400


@pytest.mark.django_db
class TestFlagListQueryCount:
    """The flag list must not issue per-flag override queries."""

    def test_override_resolution_does_not_scale_with_the_number_of_flags(
        self, client, environments, django_assert_num_queries
    ):
        for index in range(5):
            flag = FeatureFlag.objects.create(
                environment=environments["prod"], key=f"flag-{index}", name=f"F{index}"
            )
            FlagOverride.objects.create(flag=flag, is_enabled=False, reason="r")

        # Warm the session/auth queries so the count reflects the list itself.
        client.get("/api/v1/flags/")

        with django_assert_num_queries(4):
            response = client.get("/api/v1/flags/")

        assert response.status_code == 200
        assert response.data["count"] == 5
        assert all(
            row["active_override"] is not None for row in response.data["results"]
        )
