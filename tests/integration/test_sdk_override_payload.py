"""
Tests that the SDK wire format carries override state.

SDKs evaluate locally, so an override that only exists server-side would be
invisible to them. The payload must project the effective state, and it must
agree with `FlagEvaluationService` for every combination.
"""
import pytest
from rest_framework.test import APIClient

from core_flags.models import (
    Condition,
    ConditionOperator,
    Environment,
    FeatureFlag,
    FlagOverride,
    StrategyRule,
)
from core_flags.services import FlagEvaluationService


@pytest.fixture
def environment():
    return Environment.objects.create(name="Production", key="prod")


@pytest.fixture
def sdk_client(environment):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=environment.api_key)
    return client


def evaluate_locally(payload: dict) -> bool:
    """
    Mimic what an SDK does with the payload, matching FlagEvaluationService:
    disabled means false, no rules means true, otherwise any rule may match.
    """
    if not payload["is_enabled"]:
        return False
    if not payload["rules"]:
        return True
    return any(payload["rules"])


@pytest.mark.django_db
class TestSDKFlagsPayload:
    """Tests for GET /api/v1/sdk/flags/ with overrides in play."""

    def test_disabling_override_is_visible_to_the_sdk(self, sdk_client, environment):
        flag = FeatureFlag.objects.create(
            environment=environment, key="checkout", name="Checkout", is_enabled=True
        )
        FlagOverride.objects.create(flag=flag, is_enabled=False, reason="outage")

        payload = sdk_client.get("/api/v1/sdk/flags/").json()["flags"][0]

        assert payload["is_enabled"] is False
        assert payload["overridden"] is True
        assert evaluate_locally(payload) is False

    def test_enabling_override_is_visible_to_the_sdk(self, sdk_client, environment):
        flag = FeatureFlag.objects.create(
            environment=environment, key="checkout", name="Checkout", is_enabled=False
        )
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="force on")

        payload = sdk_client.get("/api/v1/sdk/flags/").json()["flags"][0]

        assert payload["is_enabled"] is True
        assert payload["overridden"] is True
        assert evaluate_locally(payload) is True

    def test_override_strips_rules_so_local_evaluation_cannot_disagree(
        self, sdk_client, environment
    ):
        flag = FeatureFlag.objects.create(
            environment=environment, key="checkout", name="Checkout", is_enabled=True
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"value": "US"},
        )
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="force on")

        payload = sdk_client.get("/api/v1/sdk/flags/").json()["flags"][0]

        assert payload["rules"] == []

    def test_lifted_override_returns_the_configured_state(
        self, sdk_client, environment
    ):
        flag = FeatureFlag.objects.create(
            environment=environment, key="checkout", name="Checkout", is_enabled=True
        )
        override = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="outage"
        )
        override.lift()

        payload = sdk_client.get("/api/v1/sdk/flags/").json()["flags"][0]

        assert payload["is_enabled"] is True
        assert payload["overridden"] is False

    def test_rules_survive_when_no_override_is_active(self, sdk_client, environment):
        flag = FeatureFlag.objects.create(
            environment=environment, key="checkout", name="Checkout", is_enabled=True
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"value": "US"},
        )

        payload = sdk_client.get("/api/v1/sdk/flags/").json()["flags"][0]

        assert len(payload["rules"]) == 1
        assert payload["rules"][0]["conditions"][0]["attribute"] == "country"

    @pytest.mark.parametrize("flag_enabled", [True, False])
    @pytest.mark.parametrize("override", [None, True, False])
    def test_payload_agrees_with_the_server_side_engine(
        self, sdk_client, environment, flag_enabled, override
    ):
        flag = FeatureFlag.objects.create(
            environment=environment,
            key="checkout",
            name="Checkout",
            is_enabled=flag_enabled,
        )
        if override is not None:
            FlagOverride.objects.create(flag=flag, is_enabled=override, reason="r")

        payload = sdk_client.get("/api/v1/sdk/flags/").json()["flags"][0]
        server_side = FlagEvaluationService().evaluate_flag(flag, {})

        assert evaluate_locally(payload) is server_side


@pytest.mark.django_db
class TestSDKEvaluateWithOverride:
    """Tests for POST /api/v1/sdk/evaluate/ with overrides in play."""

    def test_override_wins_over_a_matching_rule(self, sdk_client, environment):
        flag = FeatureFlag.objects.create(
            environment=environment, key="checkout", name="Checkout", is_enabled=True
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"value": "US"},
        )
        FlagOverride.objects.create(flag=flag, is_enabled=False, reason="outage")

        response = sdk_client.post(
            "/api/v1/sdk/evaluate/", {"context": {"country": "US"}}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["results"][0]["value"] is False
