"""
API views for core_flags.
"""
from django.db import transaction
from django.db.models import Prefetch, ProtectedError
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.api.mixins import TRUE_LITERALS, QueryParamFilterMixin
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
from tenancy.permissions import HasCapability, IsDashboardUser, TenantScopedViewSetMixin

from .serializers import (
    ConditionSerializer,
    EnvironmentSerializer,
    FeatureFlagSerializer,
    FlagOverrideSerializer,
    StrategyRuleSerializer,
    VariantSerializer,
    validate_variant_set,
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
        "variants",
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
        "variants": Capability.FLAG_EDIT,
    }

    @action(detail=True, methods=["post", "put"])
    def variants(self, request, pk=None):
        """
        Create or replace a MULTIVARIATE flag's entire variant set atomically.

        `VariantSerializer.validate` checks each row against the flag's
        *existing* rows, so it cannot express "this set of N rows sums to
        100" -- editing two rows independently means each save only sees one
        side of the change. POST creates the initial set (only when the flag
        has zero variants); PUT replaces an existing set in place, matched by
        id, so a rename, a percentage rebalance across rows, and a new
        control all land in one all-or-nothing request instead of racing
        each other through the per-row `/api/v1/variants/` endpoint.
        """
        flag = self.get_object()

        if flag.flag_type != FlagType.MULTIVARIATE:
            return Response(
                {"flag": "Variants only apply to MULTIVARIATE flags."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        variants_data = request.data.get("variants")
        if not isinstance(variants_data, list):
            return Response(
                {"variants": "This field is required and must be a list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.method == "POST":
            return self._create_variant_set(flag, variants_data)
        return self._replace_variant_set(flag, variants_data)

    def _create_variant_set(self, flag, variants_data):
        if flag.variants.exists():
            return Response(
                {"variants": "This flag already has variants. Use PUT to replace the set."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            variants_data = validate_variant_set(list(variants_data))
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            created = [
                Variant.objects.create(
                    flag=flag,
                    name=item["name"],
                    percentage_allocation=item["percentage_allocation"],
                    is_control=bool(item.get("is_control", False)),
                )
                for item in variants_data
            ]

        return Response(
            VariantSerializer(created, many=True).data, status=status.HTTP_201_CREATED
        )

    def _replace_variant_set(self, flag, variants_data):
        existing_ids = set(flag.variants.values_list("id", flat=True))
        submitted_ids = set()
        for item in variants_data:
            if not isinstance(item, dict) or "id" not in item:
                return Response(
                    {"variants": "Each variant must include the id of an existing variant on this flag."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            submitted_ids.add(str(item["id"]))

        if submitted_ids != {str(pk) for pk in existing_ids}:
            return Response(
                {
                    "variants": (
                        "The submitted set must include every existing variant on this "
                        "flag, with no additions or removals."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validated = validate_variant_set(
                [{k: v for k, v in item.items() if k != "id"} for item in variants_data]
            )
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        by_id = {str(item["id"]): validated[i] for i, item in enumerate(variants_data)}
        with transaction.atomic():
            updated = []
            for variant in flag.variants.select_for_update():
                data = by_id[str(variant.id)]
                variant.name = data["name"]
                variant.percentage_allocation = data["percentage_allocation"]
                variant.is_control = bool(data.get("is_control", False))
                variant.save(update_fields=["name", "percentage_allocation", "is_control"])
                updated.append(variant)

        return Response(VariantSerializer(updated, many=True).data, status=status.HTTP_200_OK)


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


class VariantViewSet(TenantScopedViewSetMixin, QueryParamFilterMixin, viewsets.ModelViewSet):
    """ViewSet for Variant model."""
    queryset = Variant.objects.all()
    serializer_class = VariantSerializer
    filter_fields = ("flag",)
    permission_classes = [IsDashboardUser, HasCapability]
    environment_lookup = "flag__environment"
    capability_map = {
        "create": Capability.FLAG_EDIT,
        "update": Capability.FLAG_EDIT,
        "partial_update": Capability.FLAG_EDIT,
        "destroy": Capability.FLAG_EDIT,
    }

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "This variant is forced by a strategy rule and cannot be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


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
