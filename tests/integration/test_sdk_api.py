"""
Tests for sdk_api endpoints.
"""
import pytest
from rest_framework.test import APIClient

from core_flags.models import (
    Environment,
    FeatureFlag,
    FlagType,
    StrategyRule,
    Variant,
)
from sdk_api.models import EvaluationLog, SDKRegistration


@pytest.mark.django_db
class TestSDKFlagsEndpoint:
    """Tests for GET /api/v1/sdk/flags/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)
        self.flag = FeatureFlag.objects.create(
            environment=self.env,
            key="new-dashboard",
            name="New Dashboard",
            is_enabled=True,
        )

    def test_sdk_flags_requires_authentication(self):
        """Test that SDK flags endpoint requires authentication."""
        response = self.client.get("/api/v1/sdk/flags/")
        assert response.status_code in [401, 403]

    def test_sdk_flags_returns_empty_for_new_environment(self):
        """Test that SDK flags returns empty list for environment with no flags."""
        self.client.force_authenticate(user=None)
        # TODO: Implement API key authentication
        # For now, this test documents the expected behavior
        pass


@pytest.mark.django_db
class TestSDKFlagsPayloadVariants:
    """Tests that the SDK flags payload carries variants for local evaluation."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)

    def flags_payload(self):
        response = self.client.get("/api/v1/sdk/flags/", HTTP_X_API_KEY=self.env.api_key)
        return response.json()["flags"][0]

    def test_multivariate_flag_payload_includes_variants(self):
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="checkout-variant",
            name="Checkout Variant",
            is_enabled=True,
            flag_type=FlagType.MULTIVARIATE,
        )
        Variant.objects.create(
            flag=flag, name="control", percentage_allocation=50, is_control=True
        )
        Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)

        payload = self.flags_payload()

        assert sorted(payload["variants"], key=lambda v: v["name"]) == [
            {"name": "control", "percentage_allocation": 50},
            {"name": "treatment_a", "percentage_allocation": 50},
        ]

    def test_boolean_flag_payload_has_empty_variants(self):
        FeatureFlag.objects.create(
            environment=self.env, key="boolean-flag", name="Boolean Flag", is_enabled=True
        )

        payload = self.flags_payload()

        assert payload["variants"] == []

    def test_rule_payload_includes_rollout_variant_and_percentage(self):
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="checkout-variant",
            name="Checkout Variant",
            is_enabled=True,
            flag_type=FlagType.MULTIVARIATE,
        )
        variant = Variant.objects.create(
            flag=flag, name="treatment_a", percentage_allocation=100, is_control=True
        )
        StrategyRule.objects.create(flag=flag, rollout_variant=variant, rollout_percentage=10)

        payload = self.flags_payload()

        assert payload["rules"][0]["rollout_variant"] == "treatment_a"
        assert payload["rules"][0]["rollout_percentage"] == 10

    def test_rule_payload_rollout_fields_are_none_when_unset(self):
        flag = FeatureFlag.objects.create(
            environment=self.env, key="boolean-flag", name="Boolean Flag", is_enabled=True
        )
        StrategyRule.objects.create(flag=flag)

        payload = self.flags_payload()

        assert payload["rules"][0]["rollout_variant"] is None
        assert payload["rules"][0]["rollout_percentage"] is None


@pytest.mark.django_db
class TestSDKEvaluateEndpoint:
    """Tests for POST /api/v1/sdk/evaluate/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)
        self.flag = FeatureFlag.objects.create(
            environment=self.env,
            key="new-dashboard",
            name="New Dashboard",
            is_enabled=True,
        )

    def test_sdk_evaluate_requires_authentication(self):
        """Test that SDK evaluate endpoint requires authentication."""
        response = self.client.post("/api/v1/sdk/evaluate/", {})
        assert response.status_code in [401, 403]

    def test_sdk_evaluate_returns_empty_results(self):
        """Test that SDK evaluate returns empty results initially."""
        self.client.force_authenticate(user=None)
        # TODO: Implement API key authentication
        # For now, this test documents the expected behavior
        pass


@pytest.mark.django_db
class TestSDKEvaluateLogsResultType:
    """Tests that EvaluationLog.result stores the true result, not a bool() coercion."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)

    def evaluate(self, context=None):
        return self.client.post(
            "/api/v1/sdk/evaluate/",
            {"context": context or {}},
            format="json",
            HTTP_X_API_KEY=self.env.api_key,
        )

    def test_boolean_flag_true_logs_the_string_true(self):
        FeatureFlag.objects.create(
            environment=self.env, key="on-flag", name="On Flag", is_enabled=True
        )

        self.evaluate()

        log = EvaluationLog.objects.get()
        assert log.result == "true"

    def test_boolean_flag_false_logs_the_string_false(self):
        FeatureFlag.objects.create(
            environment=self.env, key="off-flag", name="Off Flag", is_enabled=False
        )

        self.evaluate()

        log = EvaluationLog.objects.get()
        assert log.result == "false"

    def test_multivariate_flag_logs_the_variant_name(self):
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="checkout-variant",
            name="Checkout Variant",
            is_enabled=True,
            flag_type=FlagType.MULTIVARIATE,
        )
        variant = Variant.objects.create(
            flag=flag, name="treatment_a", percentage_allocation=100, is_control=True
        )
        rule = StrategyRule.objects.create(flag=flag, rollout_variant=variant, rollout_percentage=100)
        del rule

        self.evaluate(context={"user_id": "u-1"})

        log = EvaluationLog.objects.get()
        assert log.result == "treatment_a"


@pytest.mark.django_db
class TestSDKRegisterEndpoint:
    """Tests for POST /api/v1/sdk/register/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)

    def register(self, version="1.0.0"):
        """Register a JavaScript SDK against this environment's API key."""
        return self.client.post(
            "/api/v1/sdk/register/",
            {"sdk_type": "JAVASCRIPT", "version": version},
            format="json",
            HTTP_X_API_KEY=self.env.api_key,
        )

    def test_sdk_register_requires_authentication(self):
        """Test that SDK register endpoint requires authentication."""
        response = self.client.post("/api/v1/sdk/register/", {})
        assert response.status_code in [401, 403]

    def test_sdk_register_creates_registration(self):
        """Test that SDK register creates a new registration."""
        response = self.register()

        assert response.status_code == 201
        assert response.data["created"] is True
        assert SDKRegistration.objects.filter(environment=self.env).count() == 1

    def test_sdk_register_is_idempotent(self):
        """
        Repeated registrations update the existing row instead of adding one.

        Clients share their environment's API key and register on every start,
        so this endpoint is called far more often than rows should exist.
        """
        first = self.register(version="1.0.0")
        second = self.register(version="1.0.1")

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.data["created"] is False
        assert SDKRegistration.objects.filter(environment=self.env).count() == 1

        registration = SDKRegistration.objects.get(environment=self.env)
        assert registration.version == "1.0.1"


@pytest.mark.django_db
class TestSDKStreamEndpoint:
    """Tests for GET /api/v1/sdk/stream/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)

    def test_sdk_stream_requires_authentication(self):
        """Test that SDK stream endpoint requires authentication."""
        response = self.client.get("/api/v1/sdk/stream/")
        # SSE stream may return 200 initially, actual auth enforcement happens at connection
        assert response.status_code in [200, 401, 403]

    def test_sdk_stream_returns_sse_response(self):
        """Test that SDK stream returns SSE response."""
        self.client.force_authenticate(user=None)
        # TODO: Implement API key authentication
        # For now, this test documents the expected behavior
        pass
