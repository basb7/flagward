"""
API views for tenancy.

Organization/Project read scoping (design D4) proves the "Queryset Scoping
Returns 404" requirement at the top of the hierarchy. `ProjectViewSet` stays
read-only: its write path (creating/moving a `Project` between
organizations) still has no narrowed FK and would reopen a root-level hole
one level above the one this change closes (F3) -- that remains out of scope
for this slice.

`OrganizationViewSet` gains exactly one write surface: the `members` action
(slice 6, tasks 6.3/6.5), which never exposes a writable `organization` FK --
the target organization comes from the URL and is capability-checked
explicitly, not through `CapabilityScopedFKMixin`.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from tenancy.capabilities import Capability, max_seats
from tenancy.models import Organization, OrganizationMembership, Project
from tenancy.scoping import orgs_with, projects_with

from .serializers import (
    OrganizationMemberCreateSerializer,
    OrganizationMembershipSerializer,
    OrganizationSerializer,
    ProjectSerializer,
)

User = get_user_model()


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    """List, retrieve, and manage members of organizations the user can view."""

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        return orgs_with(self.request.user, Capability.ORG_VIEW)

    @action(detail=True, methods=["post"], url_path="members")
    def members(self, request, pk=None):
        """
        Create a new `auth.User` and attach it to this organization with an
        organization role (spec/organization-management: An Admin Creates and
        Attaches Users).

        Visibility (Layer 1) and the capability check (Layer 3) are kept
        distinct on purpose: an organization the requester cannot even see is
        a 404, while a visible organization the requester cannot administer
        is a 403 -- the same split every other viewset in this app makes.
        """
        organization = self.get_object()  # scoped to orgs_with(ORG_VIEW) -> 404 if invisible
        if not orgs_with(request.user, Capability.ORG_MANAGE_MEMBERS).filter(pk=organization.pk).exists():
            raise PermissionDenied()

        payload = OrganizationMemberCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        with transaction.atomic():
            # select_for_update() serializes the seat check against the
            # insert: without the row lock, two concurrent requests can both
            # read a count under the limit and both commit, oversubscribing
            # the plan.
            locked_organization = Organization.objects.select_for_update().get(pk=organization.pk)
            limit = max_seats(locked_organization.plan)
            if limit is not None:
                seat_count = OrganizationMembership.objects.filter(
                    organization=locked_organization
                ).count()
                if seat_count >= limit:
                    return Response(
                        {"error": "seat_limit_reached"}, status=status.HTTP_400_BAD_REQUEST
                    )

            new_user = User.objects.create_user(
                username=payload.validated_data["username"],
                email=payload.validated_data.get("email", ""),
                password=payload.validated_data["password"],
            )
            membership = OrganizationMembership.objects.create(
                organization=locked_organization,
                user=new_user,
                role=payload.validated_data["role"],
            )

        return Response(
            OrganizationMembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve projects the user can view."""

    queryset = Project.objects.select_related("organization")
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return projects_with(self.request.user, Capability.PROJECT_VIEW)
