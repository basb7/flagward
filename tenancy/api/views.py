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
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core_flags.models import Environment
from tenancy.capabilities import Capability, max_seats, resolve_capabilities
from tenancy.models import (
    EnvironmentMembership,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    Project,
    ProjectMembership,
)
from tenancy.scoping import environments_with, orgs_with, projects_with

from .serializers import (
    EffectiveCapabilitiesPreviewSerializer,
    EnvironmentMembershipSerializer,
    OrganizationMemberCreateSerializer,
    OrganizationMembershipSerializer,
    OrganizationMembershipUpdateSerializer,
    OrganizationSerializer,
    ProjectMembershipSerializer,
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


class OrganizationMembershipViewSet(
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    List, update (role change), and delete for `OrganizationMembership` rows.
    Creation happens through `OrganizationViewSet.members`, which also
    creates the `User` in the same request.

    Listing is scoped by `ORG_VIEW`, not `ORG_MANAGE_MEMBERS` (task 8.2/8.3):
    seeing who else shares your organization is ordinary visibility, the
    same capability that already scopes every other read in this app, not
    the administration capability the mutations below require.

    Both mutations enforce the Organization Administration Invariant
    (spec/tenancy-model): an organization must never reach zero `ADMIN`
    memberships. The check and the write share one `select_for_update()`
    transaction -- a check-then-write without the row lock lets two
    concurrent demotions of the last two admins each observe one other
    admin and both commit, leaving zero.
    """

    queryset = OrganizationMembership.objects.select_related("organization")
    serializer_class = OrganizationMembershipUpdateSerializer

    def get_serializer_class(self):
        # Reading and writing are different shapes. The update serializer
        # exists to accept a role change and pins everything else read-only;
        # using it for `list` too made the collection answer in the write
        # shape, which is how it ended up without the username the members
        # screen needs to name anyone.
        if self.action == "list":
            return OrganizationMembershipSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        # Layer 1: an organization the requester cannot even see is a 404
        # (or, for `list`, simply absent from the collection).
        return OrganizationMembership.objects.select_related("user").filter(
            organization__in=orgs_with(self.request.user, Capability.ORG_VIEW)
        )

    def _require_manage_permission(self, membership):
        # Layer 3: visible-but-unprivileged is a 403, same split as `members`.
        if not orgs_with(self.request.user, Capability.ORG_MANAGE_MEMBERS).filter(
            pk=membership.organization_id
        ).exists():
            raise PermissionDenied()

    def perform_update(self, serializer):
        membership = serializer.instance
        self._require_manage_permission(membership)
        new_role = serializer.validated_data.get("role", membership.role)
        with transaction.atomic():
            locked_admin_count = (
                OrganizationMembership.objects.select_for_update()
                .filter(organization=membership.organization, role=OrganizationRole.ADMIN)
                .count()
            )
            if (
                membership.role == OrganizationRole.ADMIN
                and new_role != OrganizationRole.ADMIN
                and locked_admin_count <= 1
            ):
                raise ValidationError({"error": "last_admin_cannot_be_demoted"})
            serializer.save()

    def perform_destroy(self, instance):
        self._require_manage_permission(instance)
        with transaction.atomic():
            locked_admin_count = (
                OrganizationMembership.objects.select_for_update()
                .filter(organization=instance.organization, role=OrganizationRole.ADMIN)
                .count()
            )
            if instance.role == OrganizationRole.ADMIN and locked_admin_count <= 1:
                raise ValidationError({"error": "last_admin_cannot_be_removed"})
            instance.delete()


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve projects the user can view."""

    queryset = Project.objects.select_related("organization")
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return projects_with(self.request.user, Capability.PROJECT_VIEW)


class ProjectMembershipViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """
    Lists and grants `ProjectMembership` roles (spec/organization-management:
    Per-Project and Per-Environment Role Grants, tasks 6.6/6.7, 8.2/8.3).

    Creation is authorized entirely by `ProjectMembershipSerializer`'s
    `CapabilityScopedFKMixin`-narrowed `project` field (design D5, Layer 2) --
    DRF has no object on a create, so there is nothing for `HasCapability` to
    check here. Listing is scoped by `PROJECT_VIEW` (task 8.2/8.3) -- ordinary
    visibility, not the `PROJECT_MANAGE_MEMBERS` capability creation requires.
    """

    queryset = ProjectMembership.objects.select_related("project__organization", "user")
    serializer_class = ProjectMembershipSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(
            project__in=projects_with(self.request.user, Capability.PROJECT_VIEW)
        )


class EnvironmentMembershipViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """
    Lists and grants `EnvironmentMembership` roles (see
    `ProjectMembershipViewSet`). Listing is scoped by `ENVIRONMENT_VIEW`
    (task 8.2/8.3) -- ordinary visibility, not the `PROJECT_MANAGE_MEMBERS`
    capability creation requires on the environment's parent project.
    """

    queryset = EnvironmentMembership.objects.select_related(
        "environment__project__organization", "user"
    )
    serializer_class = EnvironmentMembershipSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(
            environment__in=environments_with(self.request.user, Capability.ENVIRONMENT_VIEW)
        )


class EffectiveCapabilitiesPreviewView(APIView):
    """
    POST /api/v1/tenancy/effective-capabilities/preview/ (design D10, task
    6.10) -- the mitigation for the proposal's top risk: an admin composing
    project/environment grants and misreading union/carve-out semantics.

    Takes PROPOSED, unsaved roles from the body and answers through
    `resolve_capabilities` -- the exact same pure function `capabilities_for`
    calls for real enforcement. Nothing here is re-derived or duplicated, so
    the preview cannot drift from what is actually enforced.

    Requires `project.manage_members` on every project referenced, whether
    directly (`project_roles` keys) or indirectly (an environment's parent
    project in `environment_roles`) -- this is what stops the endpoint being
    used to probe organizations or projects the caller cannot administer.
    """

    def post(self, request):
        serializer = EffectiveCapabilitiesPreviewSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        organization = data["organization"]
        org_role = data["organization_role"]
        project_roles = data["project_roles"]
        environment_roles = data["environment_roles"]

        environments = {}
        referenced_project_ids = {str(pk) for pk in project_roles}
        for env_id in environment_roles:
            try:
                environment = Environment.objects.select_related("project").get(
                    pk=env_id, project__organization=organization
                )
            except (Environment.DoesNotExist, ValueError, TypeError) as exc:
                raise ValidationError(
                    {"environment_roles": f"Unknown environment in this organization: {env_id!r}"}
                ) from exc
            environments[env_id] = environment
            referenced_project_ids.add(str(environment.project_id))

        manageable_project_ids = set(
            str(pk)
            for pk in projects_with(request.user, Capability.PROJECT_MANAGE_MEMBERS)
            .filter(organization=organization)
            .values_list("pk", flat=True)
        )
        if not referenced_project_ids <= manageable_project_ids:
            raise PermissionDenied()

        results = [
            {
                "id": str(environment.id),
                "key": environment.key,
                "capabilities": sorted(
                    resolve_capabilities(
                        org_role, project_roles.get(str(environment.project_id)), environment_roles[env_id]
                    )
                ),
            }
            for env_id, environment in environments.items()
        ]

        return Response({"environments": results})
