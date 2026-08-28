"""
Analytics API views.

Thin wrappers over `analytics.services`: parse query params, return the payload.
Every endpoint accepts an optional `environment` UUID to scope the numbers.
"""
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from analytics import services


def _environment_id(request):
    """Optional `environment` query param, as a UUID or None."""
    return services.parse_uuid(request.query_params.get("environment"))


@api_view(["GET"])
def overview(request):
    """Aggregate counters for the dashboard home."""
    payload = services.build_overview(environment_id=_environment_id(request))
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
def evaluations_timeseries(request):
    """Hourly evaluation counts. Accepts `hours` (1-168, default 24)."""
    payload = services.build_evaluations_timeseries(
        hours=request.query_params.get("hours", 24),
        environment_id=_environment_id(request),
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
def top_flags(request):
    """Most evaluated flags. Accepts `hours` (1-168) and `limit` (1-50)."""
    payload = services.build_top_flags(
        hours=request.query_params.get("hours", 24),
        limit=request.query_params.get("limit", 5),
        environment_id=_environment_id(request),
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
def sdk_health(request):
    """SDK fleet health grouped by type and version."""
    payload = services.build_sdk_health(environment_id=_environment_id(request))
    return Response(payload, status=status.HTTP_200_OK)
