"""
Tests for core_flags evaluation service.
"""
import pytest

from core_flags.models import (
    Condition,
    ConditionOperator,
    Environment,
    FeatureFlag,
    FlagOverride,
    FlagType,
    OperatorLogic,
    StrategyRule,
    Variant,
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

    def test_multivariate_rule_at_100_percent_rollout_behaves_like_a_forced_variant(self):
        """A rule with rollout_percentage=100 always returns rollout_variant, no user_id needed."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        treatment = Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
            rollout_variant=treatment,
            rollout_percentage=100,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "enterprise"},
        )

        result = self.service.evaluate_flag(flag, {"plan": "enterprise"})
        assert result == "treatment_a"

    def test_multivariate_rule_with_no_rollout_percentage_behaves_like_100(self):
        """A rule with rollout_variant set but rollout_percentage left None
        must not crash: it behaves like rollout_percentage=100 (the model's
        documented default), so no user_id is needed to resolve it."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag-no-percentage",
            name="Multivariate Flag No Percentage",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        treatment = Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
            rollout_variant=treatment,
            rollout_percentage=None,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "enterprise"},
        )

        result = self.service.evaluate_flag(flag, {"plan": "enterprise"})
        assert result == "treatment_a"

    def test_multivariate_rule_with_partial_rollout_uses_its_own_percentage(self):
        """A rule's own rollout_percentage is used instead of the flag's global split."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="segment-rollout",
            name="Segment Rollout",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=100, is_control=True)
        treatment = Variant.objects.create(flag=flag, name="treatment", percentage_allocation=0)
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
            rollout_variant=treatment,
            rollout_percentage=10,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.IN_LIST,
            value={"type": "array", "value": ["pro", "enterprise"]},
        )

        # Non-matching users always fall through to the flag's global 100/0 split.
        assert self.service.evaluate_flag(flag, {"plan": "free", "user_id": "u-1"}) == "control"

        # Matching users are assigned by the RULE's 10% threshold, which the
        # global split (100% control) could never produce.
        matching_results = {
            self.service.evaluate_flag(flag, {"plan": "pro", "user_id": f"user-{i}"})
            for i in range(30)
        }
        assert "treatment" in matching_results

    def test_a_user_outside_the_rollout_window_falls_through_to_the_global_split(self):
        """A matching user whose bucket is >= rollout_percentage falls through, not to control directly."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="excluded-rollout",
            name="Excluded Rollout",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=0, is_control=True)
        treatment = Variant.objects.create(flag=flag, name="treatment", percentage_allocation=100)
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
            rollout_variant=treatment,
            rollout_percentage=10,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "pro"},
        )

        # The flag's global split is 100% treatment, so anyone falling through
        # this rule's 10% window still lands on "treatment" via the global
        # split -- proving it's a real fallthrough, not a fixed "control".
        results = {
            self.service.evaluate_flag(flag, {"plan": "pro", "user_id": f"user-{i}"})
            for i in range(30)
        }
        assert results == {"treatment"}

    def test_hash_bucket_is_the_same_regardless_of_which_flag_field_reads_it(self):
        """`_hash_bucket` depends only on (user_key, flag_key) -- it has no
        notion of "which rule matched" or "which split is active", which is
        what lets a rule's rollout_percentage be raised over time without
        reshuffling a user's underlying bucket value."""
        first = self.service._hash_bucket("u-consistent", "flag-a")
        second = self.service._hash_bucket("u-consistent", "flag-a")
        assert first == second

    def test_hash_bucket_pinned_cross_language_vectors(self):
        """These exact values are the contract the TS SDK also pins (see
        odd/tasks/sdk-multivariate-evaluation.md): both repos must agree on
        `_hash_bucket`/`hashBucket` byte-for-byte, since the SDKs evaluate the
        wire payload locally instead of asking the backend."""
        vectors = [
            ("u-1", "checkout-flow", 77.92),
            ("user-0", "checkout-flow", 77.41),
            ("user-1", "checkout-flow", 9.36),
            ("pro-user-0", "new-pricing", 55.17),
            ("ñandú-42", "new-pricing", 70.25),
            ("", "checkout-flow", 78.23),
            ("12345", "dark-mode", 35.83),
        ]
        for user_id, flag_key, expected in vectors:
            assert self.service._hash_bucket(user_id, flag_key) == expected

    def test_hash_bucket_salt_is_the_flag_key_not_the_flag_id(self):
        """Two flags that share a key in different environments (or a flag
        re-created with a new id) must bucket users identically -- the salt
        is the flag's `key`, never its database id."""
        flag_a = FeatureFlag.objects.create(
            environment=self.env,
            key="checkout-flow",
            name="Checkout Flow A",
            is_enabled=True,
        )
        other_env = Environment.objects.create(
            name="Staging", key="staging", project=self.env.project
        )
        flag_b = FeatureFlag.objects.create(
            environment=other_env,
            key="checkout-flow",
            name="Checkout Flow B",
            is_enabled=True,
        )
        assert flag_a.id != flag_b.id
        for user_id in ("u-1", "user-0", "user-1"):
            assert self.service._hash_bucket(
                user_id, flag_a.key
            ) == self.service._hash_bucket(user_id, flag_b.key)

    def test_raising_a_rules_rollout_percentage_only_ever_adds_users_never_removes(self):
        """Widening a rule's rollout_percentage keeps every user who was
        already inside it, and only adds users at the margin -- proof the
        hash bucket itself never changes when the threshold does."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="widening-rollout",
            name="Widening Rollout",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=100, is_control=True)
        treatment = Variant.objects.create(flag=flag, name="treatment", percentage_allocation=0)
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
            rollout_variant=treatment,
            rollout_percentage=10,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "pro"},
        )

        contexts = [{"plan": "pro", "user_id": f"user-{i}"} for i in range(50)]
        at_10 = {
            c["user_id"] for c in contexts if self.service.evaluate_flag(flag, c) == "treatment"
        }

        rule.rollout_percentage = 50
        rule.save(update_fields=["rollout_percentage"])

        at_50 = {
            c["user_id"] for c in contexts if self.service.evaluate_flag(flag, c) == "treatment"
        }

        assert at_10.issubset(at_50)
        assert len(at_50) > len(at_10)

    def test_multivariate_missing_user_id_returns_control_even_when_rule_has_a_rollout(self):
        """A rule-scoped rollout never defines its own control -- missing
        user_id always falls back to the flag's own control variant."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        treatment = Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
            rollout_variant=treatment,
            rollout_percentage=50,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "pro"},
        )

        result = self.service.evaluate_flag(flag, {"plan": "pro"})
        assert result == "control"

    def test_multivariate_matching_rule_without_rollout_variant_falls_through(self):
        """Test that a matching rule with no rollout_variant falls through to percentage split."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "enterprise"},
        )
        result = self.service.evaluate_flag(flag, {"plan": "enterprise", "user_id": "u-1"})
        assert result in {"control", "treatment_a"}

    def test_multivariate_no_matching_rule_uses_percentage_split(self):
        """Test that multivariate flag with no matching rules uses percentage split."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        result = self.service.evaluate_flag(flag, {"country": "AR", "user_id": "u-1"})
        assert result in {"control", "treatment_a"}

    def test_multivariate_same_user_id_returns_same_variant(self):
        """Test that the same user_id always returns the same variant."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        first = self.service.evaluate_flag(flag, {"user_id": "u-42"})
        second = self.service.evaluate_flag(flag, {"user_id": "u-42"})
        assert first == second

    def test_multivariate_missing_user_id_returns_fallback_variant(self):
        """Test that missing user_id returns the control variant."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        result = self.service.evaluate_flag(flag, {})
        assert result == "control"

    def test_multivariate_active_override_still_wins(self):
        """Test that an active FlagOverride wins over all multivariate logic."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=50, is_control=True)
        Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=50)
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="kill switch test")
        result = self.service.evaluate_flag(flag, {"user_id": "u-1"})
        assert result is True

    def test_multivariate_percentage_split_distributes_across_variants(self):
        """Triangulation: sweep many user ids against a 3-variant 33/33/34 split."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-flag",
            name="Multivariate Flag",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(flag=flag, name="control", percentage_allocation=33, is_control=True)
        Variant.objects.create(flag=flag, name="treatment_a", percentage_allocation=33)
        Variant.objects.create(flag=flag, name="treatment_b", percentage_allocation=34)

        results = [
            self.service.evaluate_flag(flag, {"user_id": f"user-{i}"})
            for i in range(20)
        ]

        assert all(r in {"control", "treatment_a", "treatment_b"} for r in results)
        assert len(set(results)) > 1


@pytest.mark.django_db
class TestPercentageSplitCondition:
    """Flagsmith-style `% Split`: the percentage gates segment entry."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)
        self.service = FlagEvaluationService()

    def _boolean_flag_with_split_rule(self, percentage, value_shape="wrapped"):
        """Boolean flag whose only rule is `plan IN [pro] AND % split`."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="gradual-flag",
            name="Gradual Flag",
            is_enabled=True,
        )
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.IN_LIST,
            value={"type": "list", "value": ["pro", "enterprise"]},
        )
        stored = {"value": percentage} if value_shape == "wrapped" else percentage
        Condition.objects.create(
            rule=rule,
            attribute="user_id",
            operator=ConditionOperator.PERCENTAGE_SPLIT,
            value=stored,
        )
        return flag

    def test_split_matches_exactly_the_bucket_under_percentage(self):
        """A boolean gradual rollout is True exactly for buckets under the split."""
        flag = self._boolean_flag_with_split_rule(60)
        for i in range(20):
            user_id = f"pro-user-{i}"
            bucket = self.service._hash_bucket(user_id, flag.key)
            result = self.service.evaluate_flag(
                flag, {"user_id": user_id, "plan": "pro"}
            )
            assert result is (bucket < 60)

    def test_split_excluded_users_never_see_the_change(self):
        """Users outside the split fall through as if the rule never matched."""
        flag = self._boolean_flag_with_split_rule(60)
        outside = [
            f"pro-user-{i}"
            for i in range(50)
            if not self.service._hash_bucket(f"pro-user-{i}", flag.key) < 60
        ]
        assert outside, "expected at least one user outside the split"
        for user_id in outside:
            assert (
                self.service.evaluate_flag(flag, {"user_id": user_id, "plan": "pro"})
                is False
            )

    def test_split_non_matching_segment_never_matches(self):
        """A free-plan user never enters, regardless of their bucket."""
        flag = self._boolean_flag_with_split_rule(100)
        for i in range(10):
            assert (
                self.service.evaluate_flag(
                    flag, {"user_id": f"free-user-{i}", "plan": "free"}
                )
                is False
            )

    def test_split_without_user_id_does_not_match(self):
        """No user_id means no bucket, so the identity does not enter."""
        flag = self._boolean_flag_with_split_rule(100)
        assert self.service.evaluate_flag(flag, {"plan": "pro"}) is False

    def test_split_accepts_raw_numeric_value_shape(self):
        """Dashboard-style raw numbers behave like the wrapped dict shape."""
        flag = self._boolean_flag_with_split_rule(100, value_shape="raw")
        assert (
            self.service.evaluate_flag(flag, {"user_id": "u-1", "plan": "pro"})
            is True
        )

    def test_split_out_of_range_value_never_matches(self):
        """A corrupt percentage is fail-closed, not fail-open."""
        flag = self._boolean_flag_with_split_rule(150)
        assert (
            self.service.evaluate_flag(flag, {"user_id": "u-1", "plan": "pro"})
            is False
        )

    def test_split_zero_matches_nobody_full_matches_segment(self):
        """Boundary: 0 enters nobody, 100 enters everyone in the segment."""
        zero = self._boolean_flag_with_split_rule(0)
        assert (
            self.service.evaluate_flag(zero, {"user_id": "u-1", "plan": "pro"})
            is False
        )

    def test_multivariate_split_plus_forced_variant(self):
        """% condition gates entry; a matched user gets the forced variant."""
        flag = FeatureFlag.objects.create(
            environment=self.env,
            key="multivariate-gradual",
            name="Multivariate Gradual",
            flag_type=FlagType.MULTIVARIATE,
            is_enabled=True,
        )
        Variant.objects.create(
            flag=flag, name="control", percentage_allocation=50, is_control=True
        )
        treatment = Variant.objects.create(
            flag=flag, name="treatment_a", percentage_allocation=50
        )
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
            rollout_variant=treatment,
            rollout_percentage=100,
        )
        Condition.objects.create(
            rule=rule,
            attribute="plan",
            operator=ConditionOperator.IN_LIST,
            value={"type": "list", "value": ["pro", "enterprise"]},
        )
        Condition.objects.create(
            rule=rule,
            attribute="user_id",
            operator=ConditionOperator.PERCENTAGE_SPLIT,
            value={"value": 60},
        )
        inside = [
            f"pro-user-{i}"
            for i in range(50)
            if self.service._hash_bucket(f"pro-user-{i}", flag.key) < 60
        ]
        assert inside, "expected at least one user inside the split"
        for user_id in inside:
            assert (
                self.service.evaluate_flag(flag, {"user_id": user_id, "plan": "pro"})
                == "treatment_a"
            )


@pytest.mark.django_db
class TestPercentageSplitValidation:
    """Serializer-level validation for the `% Split` condition value."""

    def test_valid_percentage_is_wrapped(self):
        """A raw number is normalized to the wrapped dict shape."""
        from core_flags.api.serializers import ConditionSerializer

        serializer = ConditionSerializer()
        attrs = serializer.validate(
            {
                "operator": ConditionOperator.PERCENTAGE_SPLIT,
                "value": 60,
            }
        )
        assert attrs["value"] == {"value": 60}

    def test_out_of_range_percentage_is_rejected(self):
        """Percentages outside 0-100 are rejected."""
        from rest_framework import serializers as drf_serializers

        from core_flags.api.serializers import ConditionSerializer

        serializer = ConditionSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            serializer.validate(
                {
                    "operator": ConditionOperator.PERCENTAGE_SPLIT,
                    "value": {"value": 150},
                }
            )

    def test_non_numeric_percentage_is_rejected(self):
        """Non-numeric percentages are rejected."""
        from rest_framework import serializers as drf_serializers

        from core_flags.api.serializers import ConditionSerializer

        serializer = ConditionSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            serializer.validate(
                {
                    "operator": ConditionOperator.PERCENTAGE_SPLIT,
                    "value": {"value": "a lot"},
                }
            )

    def test_other_operators_are_untouched(self):
        """Validation only applies to PERCENTAGE_SPLIT."""
        from core_flags.api.serializers import ConditionSerializer

        serializer = ConditionSerializer()
        attrs = {"operator": ConditionOperator.EQUALS, "value": "US"}
        assert serializer.validate(attrs) == attrs
