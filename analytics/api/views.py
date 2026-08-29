"""
Analytics API views.

Thin wrappers over `analytics.services`: parse query params, return the payload.
Every endpoint scopes its numbers to the environments the requesting user can
view analytics on — never a global aggregate (spec: access-control, Analytics
Scoping Is Always Bounded).
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from analytics import services
from tenancy.capabilities import Capability
from tenancy.permissions import IsDashboardUser
from tenancy.scoping import environments_with, projects_with


def _scoped_environments(request):
    """
    Environments the requesting user may view analytics on, narrowed by an
    optional `environment` or `project` filter (design D8).

    - No filter: every environment `ANALYTICS_VIEW`-visible to the user.
    - `?environment=`: malformed -> 400 (never treated as absent); parses but
      not visible (or does not exist) -> 404; visible -> that one environment.
    - `?project=`: same 400/404 split, scoped to `PROJECT_VIEW`-visible
      projects; visible -> that project's visible environments.
    """
    visible = environments_with(request.user, Capability.ANALYTICS_VIEW)

    raw_environment = request.query_params.get("environment")
    if raw_environment:
        environment_id = services.parse_uuid(raw_environment)
        if environment_id is None:
            raise ValidationError({"environment": "Not a valid UUID."})
        scoped = visible.filter(pk=environment_id)
        if not scoped.exists():
            raise NotFound()
        return scoped

    raw_project = request.query_params.get("project")
    if raw_project:
        project_id = services.parse_uuid(raw_project)
        if project_id is None:
            raise ValidationError({"project": "Not a valid UUID."})
        if not projects_with(request.user, Capability.PROJECT_VIEW).filter(pk=project_id).exists():
            raise NotFound()
        return visible.filter(project_id=project_id)

    return visible  # every environment the user can read analytics on


@api_view(["GET"])
@permission_classes([IsDashboardUser])
def overview(request):
    """Aggregate counters for the dashboard home."""
    payload = services.build_overview(_scoped_environments(request))
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsDashboardUser])
def evaluations_timeseries(request):
    """Hourly evaluation counts. Accepts `hours` (1-168, default 24)."""
    payload = services.build_evaluations_timeseries(
        _scoped_environments(request),
        hours=request.query_params.get("hours", 24),
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsDashboardUser])
def top_flags(request):
    """Most evaluated flags. Accepts `hours` (1-168) and `limit` (1-50)."""
    payload = services.build_top_flags(
        _scoped_environments(request),
        hours=request.query_params.get("hours", 24),
        limit=request.query_params.get("limit", 5),
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsDashboardUser])
def sdk_health(request):
    """SDK fleet health grouped by type and version."""
    payload = services.build_sdk_health(_scoped_environments(request))
    return Response(payload, status=status.HTTP_200_OK)
