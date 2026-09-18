"""
Serializers for core_flags API.
"""
from rest_framework import serializers

from core_flags.models import (
    Condition,
    Environment,
    FeatureFlag,
    FlagOverride,
    FlagType,
    StrategyRule,
    Variant,
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
        fields = ['id', 'flag', 'priority', 'operator_logic', 'rollout_variant', 'rollout_percentage', 'conditions']
        read_only_fields = ['id']
        extra_kwargs = {
            'rollout_variant': {'required': False, 'allow_null': True},
            'rollout_percentage': {'required': False, 'allow_null': True},
        }

    capability_scoped_fields = {
        "flag": (
            Capability.FLAG_EDIT,
            lambda user, capability: FeatureFlag.objects.filter(
                environment__in=environments_with(user, capability)
            ),
        ),
        "rollout_variant": (
            Capability.FLAG_EDIT,
            lambda user, capability: Variant.objects.filter(
                flag__environment__in=environments_with(user, capability)
            ),
        ),
    }

    def validate(self, attrs):
        if "rollout_variant" in attrs:
            rollout_variant = attrs["rollout_variant"]
        elif self.instance is not None:
            rollout_variant = self.instance.rollout_variant
        else:
            rollout_variant = None

        rollout_percentage = attrs.get(
            "rollout_percentage",
            self.instance.rollout_percentage if self.instance else None,
        )

        if rollout_variant is None:
            if rollout_percentage is not None:
                raise serializers.ValidationError(
                    {"rollout_percentage": "rollout_percentage requires a rollout_variant."}
                )
            return attrs

        flag = attrs.get("flag") or (self.instance.flag if self.instance else None)
        if rollout_variant.flag_id != flag.id:
            raise serializers.ValidationError(
                {"rollout_variant": "The rollout variant must belong to the same flag as this rule."}
            )
        if flag.flag_type != FlagType.MULTIVARIATE:
            raise serializers.ValidationError(
                {"rollout_variant": "rollout_variant only applies to MULTIVARIATE flags."}
            )

        if rollout_percentage is None:
            rollout_percentage = 100
            attrs["rollout_percentage"] = rollout_percentage
        if not (0 <= rollout_percentage <= 100):
            raise serializers.ValidationError(
                {"rollout_percentage": "rollout_percentage must be between 0 and 100."}
            )
        return attrs


def validate_variant_set(variants_data):
    """
    Whole-set validation for a flag's initial variant batch (bulk create).

    Mirrors `VariantSerializer.validate`'s rules, but against a list that has
    no rows in the database yet, so it cannot lean on `flag.variants` queries
    the way the per-row serializer does.
    """
    if not variants_data:
        raise serializers.ValidationError({"variants": "At least one variant is required."})

    for item in variants_data:
        if not isinstance(item, dict) or "name" not in item or "percentage_allocation" not in item:
            raise serializers.ValidationError(
                {"variants": "Each variant requires a name and a percentage_allocation."}
            )

    names = [item["name"] for item in variants_data]
    if len(names) != len(set(names)):
        raise serializers.ValidationError({"variants": "Variant names must be unique."})

    total = sum(item["percentage_allocation"] for item in variants_data)
    if total != 100:
        raise serializers.ValidationError(
            {"variants": f"Variant allocations must sum to 100 (currently {total})."}
        )

    if len(variants_data) == 1:
        variants_data[0]["is_control"] = True
        return variants_data

    control_count = sum(1 for item in variants_data if item.get("is_control"))
    if control_count == 0:
        raise serializers.ValidationError(
            {
                "variants": (
                    "A multivariate flag with more than one variant must "
                    "have exactly one control variant."
                )
            }
        )
    if control_count > 1:
        raise serializers.ValidationError({"variants": "A flag can only have one control variant."})

    return variants_data


class VariantSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """Serializer for Variant model."""

    class Meta:
        model = Variant
        fields = ['id', 'flag', 'name', 'percentage_allocation', 'is_control']
        read_only_fields = ['id']

    capability_scoped_fields = {
        "flag": (
            Capability.FLAG_EDIT,
            lambda user, capability: FeatureFlag.objects.filter(
                environment__in=environments_with(user, capability)
            ),
        ),
    }

    def validate(self, attrs):
        flag = attrs.get("flag") or (self.instance.flag if self.instance else None)
        if flag.flag_type != FlagType.MULTIVARIATE:
            raise serializers.ValidationError(
                {"flag": "Variants only apply to MULTIVARIATE flags."}
            )

        is_control = attrs.get(
            "is_control", self.instance.is_control if self.instance else False
        )
        is_sole_variant = self.instance is None and not flag.variants.exists()
        if is_sole_variant:
            is_control = True
            attrs["is_control"] = True

        if is_control:
            other_controls = flag.variants.filter(is_control=True)
            if self.instance is not None:
                other_controls = other_controls.exclude(pk=self.instance.pk)
            if other_controls.exists():
                raise serializers.ValidationError(
                    {"is_control": "A flag can only have one control variant."}
                )

        if not is_control:
            remaining_controls = flag.variants.filter(is_control=True)
            if self.instance is not None:
                remaining_controls = remaining_controls.exclude(pk=self.instance.pk)
            remaining_count = flag.variants.count()
            if self.instance is None:
                remaining_count += 1
            if remaining_count >= 2 and not remaining_controls.exists():
                raise serializers.ValidationError(
                    {
                        "is_control": (
                            "A multivariate flag with more than one variant must "
                            "have exactly one control variant."
                        )
                    }
                )

        percentage = attrs.get(
            "percentage_allocation",
            self.instance.percentage_allocation if self.instance else 0,
        )
        others = flag.variants.all()
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        total = sum(variant.percentage_allocation for variant in others) + percentage
        if total != 100:
            raise serializers.ValidationError(
                {"percentage_allocation": f"Variant allocations must sum to 100 (currently {total})."}
            )

        return attrs


class ActiveOverrideSerializer(serializers.ModelSerializer):
    """Compact view of the override currently forcing a flag."""
    class Meta:
        model = FlagOverride
        fields = ['id', 'is_enabled', 'reason', 'created_at']
        read_only_fields = fields


class FeatureFlagSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """Serializer for FeatureFlag model."""
    rules = StrategyRuleSerializer(many=True, read_only=True)
    variants = VariantSerializer(many=True, read_only=True)
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
            'variants',
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
