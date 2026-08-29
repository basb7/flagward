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
from tenancy.capabilities import Capability
from tenancy.permissions import HasCapability, IsDashboardUser, TenantScopedViewSetMixin

from .serializers import (
    ConditionSerializer,
    EnvironmentSerializer,
    FeatureFlagSerializer,
    FlagOverrideSerializer,
    StrategyRuleSerializer,
)


class EnvironmentViewSet(TenantScopedViewSetMixin, QueryParamFilterMixin, viewsets.ModelViewSet):
    """ViewSet for Environment model."""
    queryset = Environment.objects.select_related("project")
    serializer_class = EnvironmentSerializer
    filter_fields = ("project",)
    permission_classes = [IsDashboardUser, HasCapability]
    environment_lookup = ""  # the viewset's own model IS the environment
    capability_map = {
        "create": Capability.ENVIRONMENT_CREATE,
        "update": Capability.ENVIRONMENT_MANAGE,
        "partial_update": Capability.ENVIRONMENT_MANAGE,
        "destroy": Capability.ENVIRONMENT_DELETE,
        "rotate_api_key": Capability.ENVIRONMENT_MANAGE,
    }

    def get_permissions(self):
        # `create`'s capability (ENVIRONMENT_CREATE) lives one level up, at
        # the *project*. `HasCapability.has_permission`'s pre-check asks
        # "does environments_with(u, capability) hold anything" -- a
        # question that is only answerable against *existing* Environment
        # rows. For an Environment's own create, that check is asking about
        # the very row being created and is empty on a project's first
        # environment even when the user genuinely holds the capability.
        # Layer 2 (the narrowed `project` field on EnvironmentSerializer) is
        # already the sole create-time gate per design D5 -- this just stops
        # Layer 3's mismatched pre-check from producing a false 403 ahead of
        # it. Every other action operates on an Environment that already
        # exists, where the pre-check is meaningful, so only `create` is
        # excluded.
        if self.action == "create":
            return [permission() for permission in [IsDashboardUser]]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def rotate_api_key(self, request, pk=None):
        """Issue a fresh api_key for this environment (design F3)."""
        environment = self.get_object()
        environment.api_key = ""  # Environment.save() regenerates when blank.
        environment.save(update_fields=["api_key"])
        return Response(self.get_serializer(environment).data)


class FeatureFlagViewSet(TenantScopedViewSetMixin, QueryParamFilterMixin, viewsets.ModelViewSet):
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
    filter_fields = {
        "environment": "environment",
        "is_enabled": "is_enabled",
        "flag_type": "flag_type",
        "project": "environment__project",
    }
    boolean_filter_fields = ("is_enabled",)
    permission_classes = [IsDashboardUser, HasCapability]
    environment_lookup = "environment"
    capability_map = {
        "create": Capability.FLAG_EDIT,
        "update": Capability.FLAG_EDIT,
        "partial_update": Capability.FLAG_EDIT,
        "destroy": Capability.FLAG_EDIT,
    }


class StrategyRuleViewSet(TenantScopedViewSetMixin, QueryParamFilterMixin, viewsets.ModelViewSet):
    """ViewSet for StrategyRule model."""
    queryset = StrategyRule.objects.all()
    serializer_class = StrategyRuleSerializer
    filter_fields = ("flag",)
    permission_classes = [IsDashboardUser, HasCapability]
    environment_lookup = "flag__environment"
    capability_map = {
        "create": Capability.FLAG_EDIT,
        "update": Capability.FLAG_EDIT,
        "partial_update": Capability.FLAG_EDIT,
        "destroy": Capability.FLAG_EDIT,
    }


class ConditionViewSet(TenantScopedViewSetMixin, QueryParamFilterMixin, viewsets.ModelViewSet):
    """ViewSet for Condition model."""
    queryset = Condition.objects.all()
    serializer_class = ConditionSerializer
    filter_fields = ("rule",)
    permission_classes = [IsDashboardUser, HasCapability]
    environment_lookup = "rule__flag__environment"
    capability_map = {
        "create": Capability.FLAG_EDIT,
        "update": Capability.FLAG_EDIT,
        "partial_update": Capability.FLAG_EDIT,
        "destroy": Capability.FLAG_EDIT,
    }


class FlagOverrideViewSet(
    TenantScopedViewSetMixin,
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
    permission_classes = [IsDashboardUser, HasCapability]
    environment_lookup = "flag__environment"
    capability_map = {
        "create": Capability.OVERRIDE_MANAGE,
        "lift": Capability.OVERRIDE_MANAGE,
    }

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
