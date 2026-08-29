"""
Tests for core_flags evaluation service.
"""
import pytest

from core_flags.models import (
    Condition,
    ConditionOperator,
    Environment,
    FeatureFlag,
    FlagType,
    OperatorLogic,
    StrategyRule,
)
from core_flags.services import FlagEvaluationService


@pytest.mark.django_db
class TestFlagEvaluationService:
    """Tests for FlagEvaluationService."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)
        self.service = FlagEvaluationService()

    def test_disabled_flag_returns_false(self):
        """Test that disabled flag returns False."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="disabled-flag",
            name="Disabled Flag",
            is_enabled=False,
        )
        result = self.service.evaluate_flag(flag, {})
        assert result is False

    def test_enabled_flag_no_rules_returns_true(self):
        """Test that enabled flag with no rules returns True."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="enabled-flag",
            name="Enabled Flag",
            is_enabled=True,
        )
        result = self.service.evaluate_flag(flag, {})
        assert result is True

    def test_enabled_flag_with_matching_rule_returns_true(self):
        """Test that enabled flag with matching rule returns True."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="flag-with-rule",
            name="Flag With Rule",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
        )
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        result = self.service.evaluate_flag(flag, {"country": "US"})
        assert result is True

    def test_enabled_flag_with_non_matching_rule_returns_false(self):
        """Test that enabled flag with non-matching rule returns False."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="flag-with-rule",
            name="Flag With Rule",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
        )
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        result = self.service.evaluate_flag(flag, {"country": "AR"})
        assert result is False

    def test_and_logic_requires_all_conditions(self):
        """Test that AND logic requires all conditions to match."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="and-flag",
            name="AND Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
        )
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "premium"},
        )
        # Both conditions match
        assert self.service.evaluate_flag(flag, {"country": "US", "plan": "premium"}) is True
        # Only one condition matches
        assert self.service.evaluate_flag(flag, {"country": "US", "plan": "free"}) is False

    def test_or_logic_requires_any_condition(self):
        """Test that OR logic requires any condition to match."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="or-flag",
            name="OR Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.OR,
        )
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "premium"},
        )
        # Both conditions match
        assert self.service.evaluate_flag(flag, {"country": "US", "plan": "premium"}) is True
        # Only one condition matches
        assert self.service.evaluate_flag(flag, {"country": "US", "plan": "free"}) is True
        # No conditions match
        assert self.service.evaluate_flag(flag, {"country": "AR", "plan": "free"}) is False

    def test_equals_operator(self):
        """Test EQUALS operator."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="equals-flag",
            name="Equals Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        assert self.service.evaluate_flag(flag, {"country": "US"}) is True
        assert self.service.evaluate_flag(flag, {"country": "AR"}) is False

    def test_not_equals_operator(self):
        """Test NOT_EQUALS operator."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="not-equals-flag",
            name="Not Equals Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.NOT_EQUALS,
            value={"type": "string", "value": "US"},
        )
        assert self.service.evaluate_flag(flag, {"country": "AR"}) is True
        assert self.service.evaluate_flag(flag, {"country": "US"}) is False

    def test_greater_than_operator(self):
        """Test GREATER_THAN operator."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="gt-flag",
            name="GT Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="age",
            operator=ConditionOperator.GREATER_THAN,
            value={"type": "number", "value": 18},
        )
        assert self.service.evaluate_flag(flag, {"age": 21}) is True
        assert self.service.evaluate_flag(flag, {"age": 15}) is False

    def test_less_than_operator(self):
        """Test LESS_THAN operator."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="lt-flag",
            name="LT Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="age",
            operator=ConditionOperator.LESS_THAN,
            value={"type": "number", "value": 18},
        )
        assert self.service.evaluate_flag(flag, {"age": 15}) is True
        assert self.service.evaluate_flag(flag, {"age": 21}) is False

    def test_in_list_operator(self):
        """Test IN_LIST operator."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="in-list-flag",
            name="In List Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.IN_LIST,
            value={"type": "array", "value": ["premium", "enterprise"]},
        )
        assert self.service.evaluate_flag(flag, {"plan": "premium"}) is True
        assert self.service.evaluate_flag(flag, {"plan": "free"}) is False

    def test_contains_operator(self):
        """Test CONTAINS operator."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="contains-flag",
            name="Contains Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="tags",
            operator=ConditionOperator.CONTAINS,
            value={"type": "string", "value": "beta"},
        )
        assert self.service.evaluate_flag(flag, {"tags": ["beta", "test"]}) is True
        assert self.service.evaluate_flag(flag, {"tags": ["alpha", "stable"]}) is False

    def test_rule_priority_ordering(self):
        """Test that rules are evaluated in priority order."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="priority-flag",
            name="Priority Flag",
            is_enabled=True,
        )
        # Rule 0: country=US (matches)
        rule0 = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule0,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        # Rule 1: country=AR (doesn't match)
        rule1 = StrategyRule.objects.create(flag=flag, priority=1, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule1,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "AR"},
        )
        # Should return True because rule0 matches first
        assert self.service.evaluate_flag(flag, {"country": "US"}) is True

    def test_multivariate_flag_returns_variant(self):
        """Test that multivariate flag returns variant name."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        result = self.service.evaluate_flag(flag, {"country": "US"})
        assert result is True  # For now, return True for matching rules

    def test_multivariate_flag_no_match_returns_control(self):
        """Test that multivariate flag returns control when no rules match."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        result = self.service.evaluate_flag(flag, {"country": "AR"})
        assert result is False  # Control variant
