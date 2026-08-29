"""
Tests for core_flags models.
"""
import uuid

import pytest
from django.db import IntegrityError

from core_flags.models import (
    Condition,
    ConditionOperator,
    Environment,
    FeatureFlag,
    FlagOverride,
    FlagType,
    OperatorLogic,
    StrategyRule,
)


@pytest.mark.django_db
class TestEnvironmentTenancy:
    """Tests for the Environment/Project tenancy relationship."""

    def test_environment_requires_project(self):
        """An environment with no project is rejected at the database level."""
        with pytest.raises(IntegrityError):
            Environment.objects.create(name="Production", key="production")

    def test_two_projects_can_each_hold_production(self, make_project):
        """Uniqueness is scoped to (project, key), not global."""
        project_a = make_project()
        project_b = make_project()

        env_a = Environment.objects.create(name="Production", key="production", project=project_a)
        env_b = Environment.objects.create(name="Production", key="production", project=project_b)

        assert env_a.project == project_a
        assert env_b.project == project_b


@pytest.mark.django_db
class TestEnvironment:
    """Tests for Environment model."""

    def test_create_environment(self, project):
        """Test creating an environment with valid data."""
        env = Environment.objects.create(
            name="Production",
            key="production",
            project=project,
        )
        assert env.id is not None
        assert isinstance(env.id, uuid.UUID)
        assert env.name == "Production"
        assert env.key == "production"
        assert env.api_key is not None
        assert len(env.api_key) > 0

    def test_environment_api_key_unique(self, project):
        """Test that api_key is unique."""
        env1 = Environment.objects.create(name="Env1", key="env1", project=project)
        env2 = Environment.objects.create(name="Env2", key="env2", project=project)
        assert env1.api_key != env2.api_key

    def test_environment_key_unique_together(self, project):
        """Test that key is unique per environment."""
        Environment.objects.create(name="Env1", key="env1", project=project)
        with pytest.raises(IntegrityError):
            Environment.objects.create(name="Env2", key="env1", project=project)

    def test_environment_str(self, project):
        """Test environment string representation."""
        env = Environment.objects.create(name="Production", key="prod", project=project)
        assert str(env) == "Production"

    def test_environment_api_key_auto_generated(self, project):
        """Test that api_key is auto-generated if not provided."""
        env = Environment.objects.create(name="Test", key="test", project=project)
        assert env.api_key is not None
        assert len(env.api_key) == 32  # UUID without hyphens


@pytest.mark.django_db
class TestFeatureFlag:
    """Tests for FeatureFlag model."""

    def test_create_feature_flag(self, project):
        """Test creating a feature flag with valid data."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(
            environment=env,
            key="new-dashboard",
            name="New Dashboard",
            description="Enable new dashboard",
        )
        assert flag.id is not None
        assert isinstance(flag.id, uuid.UUID)
        assert flag.environment == env
        assert flag.key == "new-dashboard"
        assert flag.name == "New Dashboard"
        assert flag.is_enabled is False
        assert flag.flag_type == FlagType.BOOLEAN

    def test_feature_flag_unique_together(self, project):
        """Test that flag key is unique per environment."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        with pytest.raises(IntegrityError):
            FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1 Duplicate")

    def test_feature_flag_cascade_delete(self, project):
        """Test that deleting environment cascades to flags."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        env.delete()
        assert FeatureFlag.objects.count() == 0

    def test_feature_flag_str(self, project):
        """Test feature flag string representation."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        assert str(flag) == "prod/flag1"

    def test_feature_flag_multivariate_type(self, project):
        """Test creating a multivariate flag."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(
            environment=env,
            key="experiment",
            name="Experiment",
            flag_type=FlagType.MULTIVARIATE,
        )
        assert flag.flag_type == FlagType.MULTIVARIATE


@pytest.mark.django_db
class TestStrategyRule:
    """Tests for StrategyRule model."""

    def test_create_strategy_rule(self, project):
        """Test creating a strategy rule with valid data."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        rule = StrategyRule.objects.create(
            flag=flag,
            priority=0,
            operator_logic=OperatorLogic.AND,
        )
        assert rule.id is not None
        assert isinstance(rule.id, uuid.UUID)
        assert rule.flag == flag
        assert rule.priority == 0
        assert rule.operator_logic == OperatorLogic.AND

    def test_strategy_rule_cascade_delete(self, project):
        """Test that deleting flag cascades to rules."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        flag.delete()
        assert StrategyRule.objects.count() == 0

    def test_strategy_rule_str(self, project):
        """Test strategy rule string representation."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        assert str(rule) == "Rule 0 for prod/flag1"

    def test_strategy_rule_ordering(self, project):
        """Test that rules are ordered by priority."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        rule2 = StrategyRule.objects.create(flag=flag, priority=2, operator_logic=OperatorLogic.AND)
        rule0 = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.OR)
        rule1 = StrategyRule.objects.create(flag=flag, priority=1, operator_logic=OperatorLogic.AND)
        rules = list(flag.rules.all())
        assert rules[0] == rule0
        assert rules[1] == rule1
        assert rules[2] == rule2


@pytest.mark.django_db
class TestCondition:
    """Tests for Condition model."""

    def test_create_condition(self, project):
        """Test creating a condition with valid data."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        condition = Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        assert condition.id is not None
        assert isinstance(condition.id, uuid.UUID)
        assert condition.rule == rule
        assert condition.attribute == "country"
        assert condition.operator == ConditionOperator.EQUALS
        assert condition.value == {"type": "string", "value": "US"}

    def test_condition_cascade_delete(self, project):
        """Test that deleting rule cascades to conditions."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        rule.delete()
        assert Condition.objects.count() == 0

    def test_condition_str(self, project):
        """Test condition string representation."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)
        condition = Condition.objects.create(
            rule=rule,
            attribute="country",
            operator=ConditionOperator.EQUALS,
            value={"type": "string", "value": "US"},
        )
        assert str(condition) == "country EQUALS {'type': 'string', 'value': 'US'}"

    def test_condition_value_types(self, project):
        """Test condition with different value types."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        rule = StrategyRule.objects.create(flag=flag, priority=0, operator_logic=OperatorLogic.AND)

        # Number value
        condition_number = Condition.objects.create(
            rule=rule,
            attribute="age",
            operator=ConditionOperator.GREATER_THAN,
            value={"type": "number", "value": 18},
        )
        assert condition_number.value == {"type": "number", "value": 18}

        # Array value
        condition_array = Condition.objects.create(
            rule=rule,
            attribute="tags",
            operator=ConditionOperator.IN_LIST,
            value={"type": "array", "value": ["beta", "test"]},
        )
        assert condition_array.value == {"type": "array", "value": ["beta", "test"]}


@pytest.mark.django_db
class TestFlagOverride:
    """Tests for FlagOverride model."""

    def test_create_flag_override(self, project):
        """Test creating a flag override."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        override = FlagOverride.objects.create(
            flag=flag,
            is_enabled=True,
            reason="Emergency rollback",
        )
        assert override.id is not None
        assert isinstance(override.id, uuid.UUID)
        assert override.flag == flag
        assert override.is_enabled is True
        assert override.reason == "Emergency rollback"

    def test_flag_override_str(self, project):
        """Test flag override string representation."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        override = FlagOverride.objects.create(
            flag=flag,
            is_enabled=False,
            reason="Disable for maintenance",
        )
        assert str(override) == "Override for prod/flag1"

    def test_flag_override_cascade_delete(self, project):
        """Test that deleting flag cascades to overrides."""
        env = Environment.objects.create(name="Prod", key="prod", project=project)
        flag = FeatureFlag.objects.create(environment=env, key="flag1", name="Flag1")
        FlagOverride.objects.create(flag=flag, is_enabled=True, reason="Test")
        flag.delete()
        assert FlagOverride.objects.count() == 0
