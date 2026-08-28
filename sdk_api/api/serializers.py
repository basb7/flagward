"""
Serializers for the SDK monitoring API (dashboard-facing).
"""
from rest_framework import serializers

from sdk_api.models import EvaluationLog, SDKRegistration


class SDKRegistrationSerializer(serializers.ModelSerializer):
    """Read model for a registered SDK instance."""

    environment_key = serializers.CharField(source="environment.key", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)

    class Meta:
        model = SDKRegistration
        fields = [
            "id",
            "environment",
            "environment_key",
            "environment_name",
            "sdk_type",
            "sdk_key",
            "version",
            "last_seen_at",
            "created_at",
        ]
        read_only_fields = fields


class EvaluationLogSerializer(serializers.ModelSerializer):
    """Read model for a single flag evaluation."""

    flag_key = serializers.CharField(source="flag.key", read_only=True)
    flag_name = serializers.CharField(source="flag.name", read_only=True)
    environment = serializers.PrimaryKeyRelatedField(
        source="flag.environment", read_only=True
    )
    environment_key = serializers.CharField(source="flag.environment.key", read_only=True)

    class Meta:
        model = EvaluationLog
        fields = [
            "id",
            "flag",
            "flag_key",
            "flag_name",
            "environment",
            "environment_key",
            "context_hash",
            "result",
            "timestamp",
        ]
        read_only_fields = fields
