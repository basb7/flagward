"""
Services for core_flags evaluation engine.
"""
from typing import Any

from core_flags.models import (
    Condition,
    ConditionOperator,
    FeatureFlag,
    FlagOverride,
    StrategyRule,
)


class FlagEvaluationService:
    """Service for evaluating feature flags."""

    def evaluate_flag(self, flag: FeatureFlag, context: dict[str, Any]) -> Any:
        """
        Evaluate a feature flag with the given context.

        Args:
            flag: The feature flag to evaluate
            context: Dictionary of attributes to evaluate against

        An active override wins over both `flag.is_enabled` and the targeting
        rules: it is a forced value, so there is nothing left to evaluate.

        Returns:
            Boolean result for BOOLEAN flags, or variant name for MULTIVARIATE flags
        """
        override = FlagOverride.objects.active_for(flag)
        if override is not None:
            return override.is_enabled

        if not flag.is_enabled:
            return False

        rules = flag.rules.all().order_by("priority")

        if not rules.exists():
            return True

        for rule in rules:
            result = self._evaluate_rule(rule, context)
            if result:
                return True

        return False

    def _evaluate_rule(self, rule: StrategyRule, context: dict[str, Any]) -> bool:
        """
        Evaluate a strategy rule with the given context.

        Args:
            rule: The strategy rule to evaluate
            context: Dictionary of attributes to evaluate against

        Returns:
            Boolean result based on operator logic
        """
        conditions = rule.conditions.all()

        if not conditions.exists():
            return True

        if rule.operator_logic == "AND":
            return all(self._evaluate_condition(c, context) for c in conditions)
        else:  # OR
            return any(self._evaluate_condition(c, context) for c in conditions)

    def _evaluate_condition(self, condition: Condition, context: dict[str, Any]) -> bool:
        """
        Evaluate a condition with the given context.

        Args:
            condition: The condition to evaluate
            context: Dictionary of attributes to evaluate against

        Returns:
            Boolean result based on operator
        """
        attribute_value = context.get(condition.attribute)

        if attribute_value is None:
            return False

        expected_value = condition.value.get("value")

        if expected_value is None:
            return False

        operator = condition.operator

        if operator == ConditionOperator.EQUALS:
            return attribute_value == expected_value
        elif operator == ConditionOperator.NOT_EQUALS:
            return attribute_value != expected_value
        elif operator == ConditionOperator.GREATER_THAN:
            return attribute_value > expected_value
        elif operator == ConditionOperator.LESS_THAN:
            return attribute_value < expected_value
        elif operator == ConditionOperator.IN_LIST:
            return attribute_value in expected_value
        elif operator == ConditionOperator.CONTAINS:
            return expected_value in attribute_value
        else:
            return False
