"""
Serializers for core_flags API.
"""
from rest_framework import serializers

from core_flags.models import (
    Condition,
    Environment,
    FeatureFlag,
    FlagOverride,
    StrategyRule,
)
from tenancy.capabilities import Capability
from tenancy.scoping import environments_with, projects_with
from tenancy.serializers import CapabilityScopedFKMixin, DerivedKeyMixin


class EnvironmentSerializer(DerivedKeyMixin, CapabilityScopedFKMixin, serializers.ModelSerializer):
    """
    Serializer for Environment model.

    `key` is derived from `name` on create (see `DerivedKeyMixin`) and stays
    writable so the rename dialog can edit it.
    """
    class Meta:
        model = Environment
        fields = ['id', 'name', 'key', 'api_key', 'project']
        read_only_fields = ['id', 'api_key']
        extra_kwargs = {'key': {'required': False}}

    # F3 -- the root of the FK-narrowing chain. Without this, any
    # authenticated user could POST an environment into another
    # organization's project by UUID.
    capability_scoped_fields = {
        "project": (Capability.ENVIRONMENT_CREATE, projects_with),
    }

    def derived_key_queryset(self, attrs):
        # `unique_together = ("project", "key")` scopes uniqueness to the
        # project: two projects may each have their own `production`.
        return Environment.objects.filter(project=attrs["project"])


class ConditionSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """Serializer for Condition model."""
    class Meta:
        model = Condition
        fields = ['id', 'rule', 'attribute', 'operator', 'value']
        read_only_fields = ['id']

    capability_scoped_fields = {
        "rule": (
            Capability.FLAG_EDIT,
            lambda user, capability: StrategyRule.objects.filter(
                flag__environment__in=environments_with(user, capability)
            ),
        ),
    }


class StrategyRuleSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """Serializer for StrategyRule model."""
    conditions = ConditionSerializer(many=True, read_only=True)

    class Meta:
        model = StrategyRule
        fields = ['id', 'flag', 'priority', 'operator_logic', 'conditions']
        read_only_fields = ['id']

    capability_scoped_fields = {
        "flag": (
            Capability.FLAG_EDIT,
            lambda user, capability: FeatureFlag.objects.filter(
                environment__in=environments_with(user, capability)
            ),
        ),
    }


class ActiveOverrideSerializer(serializers.ModelSerializer):
    """Compact view of the override currently forcing a flag."""
    class Meta:
        model = FlagOverride
        fields = ['id', 'is_enabled', 'reason', 'created_at']
        read_only_fields = fields


class FeatureFlagSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """Serializer for FeatureFlag model."""
    rules = StrategyRuleSerializer(many=True, read_only=True)
    active_override = serializers.SerializerMethodField()
    effective_is_enabled = serializers.SerializerMethodField()

    class Meta:
        model = FeatureFlag
        fields = [
            'id',
            'environment',
            'key',
            'name',
            'description',
            'is_enabled',
            'effective_is_enabled',
            'active_override',
            'flag_type',
            'rules',
        ]
        read_only_fields = ['id', 'effective_is_enabled', 'active_override']

    capability_scoped_fields = {
        "environment": (Capability.FLAG_EDIT, environments_with),
    }

    @staticmethod
    def _active_override(flag):
        """
        The override forcing this flag.

        Reads `active_overrides` when the viewset prefetched it — resolving per
        instance turns a flag list into an N+1.
        """
        prefetched = getattr(flag, "active_overrides", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return FlagOverride.objects.active_for(flag)

    def get_active_override(self, flag):
        override = self._active_override(flag)
        return ActiveOverrideSerializer(override).data if override else None

    def get_effective_is_enabled(self, flag) -> bool:
        """What the SDKs actually see: the override's value when one is active."""
        override = self._active_override(flag)
        return override.is_enabled if override else flag.is_enabled


class FlagOverrideSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """Serializer for FlagOverride model."""
    flag_key = serializers.CharField(source='flag.key', read_only=True)
    flag_name = serializers.CharField(source='flag.name', read_only=True)
    environment = serializers.PrimaryKeyRelatedField(source='flag.environment', read_only=True)
    environment_key = serializers.CharField(source='flag.environment.key', read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    capability_scoped_fields = {
        "flag": (
            Capability.OVERRIDE_MANAGE,
            lambda user, capability: FeatureFlag.objects.filter(
                environment__in=environments_with(user, capability)
            ),
        ),
    }

    class Meta:
        model = FlagOverride
        fields = [
            'id',
            'flag',
            'flag_key',
            'flag_name',
            'environment',
            'environment_key',
            'is_enabled',
            'is_active',
            'reason',
            'created_at',
            'cleared_at',
        ]
        read_only_fields = [
            'id',
            'flag_key',
            'flag_name',
            'environment',
            'environment_key',
            'is_active',
            'created_at',
            'cleared_at',
        ]
