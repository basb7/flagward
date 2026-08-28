"""
Dashboard-facing views for SDK monitoring.

These endpoints are read-only on purpose: SDK registrations and evaluation logs
are produced by the SDK surface (`/api/v1/sdk/`), never edited by a human.
"""
from rest_framework import viewsets

from core.api.mixins import QueryParamFilterMixin
from sdk_api.models import EvaluationLog, SDKRegistration

from .serializers import EvaluationLogSerializer, SDKRegistrationSerializer


class SDKRegistrationViewSet(QueryParamFilterMixin, viewsets.ReadOnlyModelViewSet):
    """List and retrieve registered SDK instances."""

    queryset = SDKRegistration.objects.select_related("environment").order_by(
        "-last_seen_at"
    )
    serializer_class = SDKRegistrationSerializer
    filter_fields = ("environment", "sdk_type", "version")


class EvaluationLogViewSet(QueryParamFilterMixin, viewsets.ReadOnlyModelViewSet):
    """List and retrieve flag evaluation logs."""

    queryset = EvaluationLog.objects.select_related("flag", "flag__environment")
    serializer_class = EvaluationLogSerializer
    filter_fields = {
        "flag": "flag",
        "result": "result",
        "environment": "flag__environment",
    }
    boolean_filter_fields = ("result",)
