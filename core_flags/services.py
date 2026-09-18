"""
Services for core_flags evaluation engine.
"""
import hashlib
from typing import Any

from core_flags.models import (
    Condition,
    ConditionOperator,
    FeatureFlag,
    FlagOverride,
    FlagType,
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

        if flag.flag_type == FlagType.MULTIVARIATE:
            return self._evaluate_multivariate(flag, rules, context)

        if not rules.exists():
            return True

        for rule in rules:
            result = self._evaluate_rule(rule, context)
            if result:
                return True

        return False

    def _evaluate_multivariate(
        self, flag: FeatureFlag, rules, context: dict[str, Any]
    ) -> str:
        """
        Evaluate a MULTIVARIATE flag: a matching rule with its own rollout wins
        for the share of users under `rollout_percentage`; everyone else --
        excluded from that rollout, matched a rule with no rollout of its own,
        or matched no rule at all -- falls through to the flag's global
        percentage split.
        """
        for rule in rules:
            if not self._evaluate_rule(rule, context):
                continue

            if rule.rollout_variant is None:
                break

            if rule.rollout_percentage is not None and rule.rollout_percentage >= 100:
                # Every bucket value satisfies "< 100", so no hash -- and no
                # user_id -- is needed to resolve this rule.
                return rule.rollout_variant.name

            user_key = context.get("user_id")
            if user_key is None:
                return flag.variants.get(is_control=True).name

            if self._hash_bucket(user_key, flag.id) < rule.rollout_percentage:
                return rule.rollout_variant.name

            break

        return self._assign_by_percentage(flag, context)

    def _hash_bucket(self, user_key: str, flag_id) -> float:
        """Hash a user key + flag id into a deterministic float in [0, 100)."""
        digest = hashlib.md5(f"{user_key}:{flag_id}".encode()).hexdigest()
        return int(digest[:8], 16) % 10000 / 100.0

    def _assign_by_percentage(self, flag: FeatureFlag, context: dict[str, Any]) -> str:
        """Assign a variant deterministically by the flag's global percentage allocation."""
        user_key = context.get("user_id")
        variants = flag.variants.order_by("id")

        if user_key is None:
            return flag.variants.get(is_control=True).name

        bucket_value = self._hash_bucket(user_key, flag.id)

        cumulative = 0.0
        for variant in variants:
            cumulative += variant.percentage_allocation
            if bucket_value < cumulative:
                return variant.name

        return variants.last().name

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
