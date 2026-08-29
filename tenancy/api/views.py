"""
API views for tenancy.

Read-only in this slice: Organization/Project scoping (design D4) proves the
"Queryset Scoping Returns 404" requirement at the top of the hierarchy. Write
endpoints (grants, seat-limited member creation) are slice 6's job -- adding
them here without a narrowed `organization` FK on `ProjectSerializer` would
reopen a root-level hole one level above the one this change closes (F3).
"""
from rest_framework import viewsets

from tenancy.capabilities import Capability
from tenancy.models import Organization, Project
from tenancy.scoping import orgs_with, projects_with

from .serializers import OrganizationSerializer, ProjectSerializer


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve organizations the user can view."""

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        return orgs_with(self.request.user, Capability.ORG_VIEW)


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve projects the user can view."""

    queryset = Project.objects.select_related("organization")
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return projects_with(self.request.user, Capability.PROJECT_VIEW)
