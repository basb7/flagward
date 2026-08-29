"""
Dashboard-facing views for SDK monitoring.

These endpoints are read-only on purpose: SDK registrations and evaluation logs
are produced by the SDK surface (`/api/v1/sdk/`), never edited by a human.
"""
from rest_framework import viewsets

from core.api.mixins import QueryParamFilterMixin
from sdk_api.models import EvaluationLog, SDKRegistration
from tenancy.permissions import TenantScopedViewSetMixin

from .serializers import EvaluationLogSerializer, SDKRegistrationSerializer


class SDKRegistrationViewSet(
    TenantScopedViewSetMixin, QueryParamFilterMixin, viewsets.ReadOnlyModelViewSet
):
    """List and retrieve registered SDK instances."""

    queryset = SDKRegistration.objects.select_related("environment").order_by(
        "-last_seen_at"
    )
    serializer_class = SDKRegistrationSerializer
    filter_fields = ("environment", "sdk_type", "version")
    environment_lookup = "environment"
    capability_map = {}  # read-only viewset: no unsafe action ever reaches HasCapability


class EvaluationLogViewSet(
    TenantScopedViewSetMixin, QueryParamFilterMixin, viewsets.ReadOnlyModelViewSet
):
    """List and retrieve flag evaluation logs."""

    queryset = EvaluationLog.objects.select_related("flag", "flag__environment")
    serializer_class = EvaluationLogSerializer
    filter_fields = {
        "flag": "flag",
        "result": "result",
        "environment": "flag__environment",
    }
    boolean_filter_fields = ("result",)
    environment_lookup = "flag__environment"
    capability_map = {}
