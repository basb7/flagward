"""
API views for core_flags.
"""
from django.db import transaction
from django.db.models import Prefetch
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.api.mixins import TRUE_LITERALS, QueryParamFilterMixin
from core_flags.models import (
    Condition,
    Environment,
    FeatureFlag,
    FlagOverride,
    StrategyRule,
)

from .serializers import (
    ConditionSerializer,
    EnvironmentSerializer,
    FeatureFlagSerializer,
    FlagOverrideSerializer,
    StrategyRuleSerializer,
)


class EnvironmentViewSet(viewsets.ModelViewSet):
    """ViewSet for Environment model."""
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer


class FeatureFlagViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """ViewSet for FeatureFlag model."""
    queryset = FeatureFlag.objects.select_related("environment").prefetch_related(
        "rules",
        "rules__conditions",
        Prefetch(
            "overrides",
            queryset=FlagOverride.objects.active().order_by("-created_at"),
            to_attr="active_overrides",
        ),
    )
    serializer_class = FeatureFlagSerializer
    filter_fields = ("environment", "is_enabled", "flag_type")
    boolean_filter_fields = ("is_enabled",)


class StrategyRuleViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """ViewSet for StrategyRule model."""
    queryset = StrategyRule.objects.all()
    serializer_class = StrategyRuleSerializer
    filter_fields = ("flag",)


class ConditionViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """ViewSet for Condition model."""
    queryset = Condition.objects.all()
    serializer_class = ConditionSerializer
    filter_fields = ("rule",)


class FlagOverrideViewSet(
    QueryParamFilterMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Manual flag overrides (the kill switch).

    While active, an override forces the flag's value in the evaluation engine.
    It never rewrites the flag's own `is_enabled`, so lifting it returns the flag
    to its configured state.

    Rows are never edited or deleted — that is what keeps the trail of who forced
    what and why. To stop an override, POST to its `lift/` action; to change one,
    record a new override, which lifts the previous active one for that flag.

    Filters: `?flag=`, `?environment=`, `?is_enabled=`, `?active=true|false`.
    """

    queryset = FlagOverride.objects.select_related("flag", "flag__environment")
    serializer_class = FlagOverrideSerializer
    filter_fields = {
        "flag": "flag",
        "environment": "flag__environment",
        "is_enabled": "is_enabled",
    }
    boolean_filter_fields = ("is_enabled",)

    def get_queryset(self):
        queryset = super().get_queryset()

        # `active` maps to "cleared_at is null", so it cannot go through the
        # exact-match filter mixin.
        active = self.request.query_params.get("active")
        if active is not None:
            wants_active = active.strip().lower() in TRUE_LITERALS
            queryset = queryset.filter(cleared_at__isnull=wants_active)

        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        flag = serializer.validated_data["flag"]

        # One active override per flag: a new one supersedes the previous.
        for previous in FlagOverride.objects.active().filter(flag=flag):
            previous.lift()

        serializer.save()

    @action(detail=True, methods=["post"])
    def lift(self, request, pk=None):
        """Stop forcing the flag. The row stays in the trail, stamped as lifted."""
        override = self.get_object()
        override.lift()
        return Response(self.get_serializer(override).data)
