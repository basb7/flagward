"""
Tests for flag override precedence in the evaluation service.

An override is a forced value: while it is active it wins over the flag's own
`is_enabled` AND bypasses targeting rules. Lifting it returns the flag to the
state it was configured with.
"""
import pytest

from core_flags.models import (
    Condition,
    ConditionOperator,
    Environment,
    FeatureFlag,
    FlagOverride,
    StrategyRule,
)
from core_flags.services import FlagEvaluationService


@pytest.mark.django_db
class TestOverridePrecedence:
    """Tests for FlagEvaluationService with an active override."""

    def setup_method(self):
        self.env = Environment.objects.create(name="Prod", key="prod")
        self.service = FlagEvaluationService()

    def _flag(self, *, is_enabled):
        return FeatureFlag.objects.create(
            environment=self.env,
            key="checkout",
            name="Checkout",
            is_enabled=is_enabled,
        )

    def test_disabling_override_beats_an_enabled_flag(self):
        flag = self._flag(is_enabled=True)
        FlagOverride.objects.create(flag=flag, is_enabled=False, reason="outage")

        assert self.service.evaluate_flag(flag, {}) is False

    def test_enabling_override_beats_a_disabled_flag(self):
        flag = self._flag(is_enabled=False)
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="force on")

        assert self.service.evaluate_flag(flag, {}) is True

    def test_override_does_not_change_the_configured_flag_state(self):
        flag = self._flag(is_enabled=True)
        FlagOverride.objects.create(flag=flag, is_enabled=False, reason="outage")

        flag.refresh_from_db()
        assert flag.is_enabled is True, "the override must not overwrite configuration"

    def test_disabling_override_bypasses_a_matching_rule(self):
        flag = self._flag(is_enabled=True)
        rule = StrategyRule.objects.create(flag=flag, priority=0)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"value": "US"},
        )
        FlagOverride.objects.create(flag=flag, is_enabled=False, reason="outage")

        assert self.service.evaluate_flag(flag, {"country": "US"}) is False

    def test_enabling_override_bypasses_a_non_matching_rule(self):
        flag = self._flag(is_enabled=True)
        rule = StrategyRule.objects.create(flag=flag, priority=0)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"value": "US"},
        )
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="force on")

        assert self.service.evaluate_flag(flag, {"country": "AR"}) is True

    def test_lifted_override_stops_applying(self):
        flag = self._flag(is_enabled=True)
        override = FlagOverride.objects.create(
            flag=flag, is_enabled=False, reason="outage"
        )
        override.lift()

        assert self.service.evaluate_flag(flag, {}) is True

    def test_latest_active_override_wins(self):
        flag = self._flag(is_enabled=True)
        first = FlagOverride.objects.create(flag=flag, is_enabled=False, reason="off")
        first.lift()
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="back on")

        assert self.service.evaluate_flag(flag, {}) is True

    def test_an_override_on_another_flag_is_ignored(self):
        flag = self._flag(is_enabled=True)
        other = FeatureFlag.objects.create(
            environment=self.env, key="other", name="Other", is_enabled=True
        )
        FlagOverride.objects.create(flag=other, is_enabled=False, reason="outage")

        assert self.service.evaluate_flag(flag, {}) is True


@pytest.mark.django_db
class TestFlagOverrideModel:
    """Tests for the override queryset helpers."""

    def setup_method(self):
        self.env = Environment.objects.create(name="Prod", key="prod")
        self.flag = FeatureFlag.objects.create(
            environment=self.env, key="checkout", name="Checkout", is_enabled=True
        )

    def test_new_override_is_active(self):
        override = FlagOverride.objects.create(
            flag=self.flag, is_enabled=False, reason="outage"
        )

        assert override.is_active is True
        assert override.cleared_at is None
        assert FlagOverride.objects.active().count() == 1

    def test_lift_marks_it_cleared(self):
        override = FlagOverride.objects.create(
            flag=self.flag, is_enabled=False, reason="outage"
        )

        override.lift()

        override.refresh_from_db()
        assert override.is_active is False
        assert override.cleared_at is not None
        assert FlagOverride.objects.active().count() == 0

    def test_lift_is_idempotent(self):
        override = FlagOverride.objects.create(
            flag=self.flag, is_enabled=False, reason="outage"
        )
        override.lift()
        first_cleared_at = override.cleared_at

        override.lift()

        override.refresh_from_db()
        assert override.cleared_at == first_cleared_at

    def test_active_for_returns_the_newest_active_override(self):
        old = FlagOverride.objects.create(
            flag=self.flag, is_enabled=False, reason="old"
        )
        old.lift()
        newest = FlagOverride.objects.create(
            flag=self.flag, is_enabled=True, reason="newest"
        )

        assert FlagOverride.objects.active_for(self.flag) == newest

    def test_active_for_returns_none_without_an_active_override(self):
        assert FlagOverride.objects.active_for(self.flag) is None
