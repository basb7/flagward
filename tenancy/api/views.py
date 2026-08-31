"""
API views for tenancy.

Organization/Project read scoping (design D4) proves the "Queryset Scoping
Returns 404" requirement at the top of the hierarchy.

`OrganizationViewSet.create` has no capability to check and no FK to narrow:
an organization has no parent tenant, so any authenticated user may create
one and becomes its `ADMIN` in the same transaction -- the membership
creation is not optional and not a second request, since a user must never
end up with an organization it cannot administer.

`ProjectViewSet.create`'s `organization` FK is narrowed through
`ProjectSerializer`'s `CapabilityScopedFKMixin` (design D5, Layer 2 -- the
only create-time gate, since DRF's permission class has no object on
`POST`) to organizations where the requester holds `Capability.PROJECT_CREATE`.
An unnarrowed FK here would reopen exactly the root-level hole the tenancy
change closed (F3), one level above it.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core_flags.models import Environment
from tenancy.capabilities import Capability, max_seats, resolve_capabilities
from tenancy.models import (
    EnvironmentMembership,
    Invitation,
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
    EnvironmentMembershipUpdateSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    OrganizationMembershipSerializer,
    OrganizationMembershipUpdateSerializer,
    OrganizationSerializer,
    ProjectMembershipSerializer,
    ProjectMembershipUpdateSerializer,
    ProjectSerializer,
)


class OrganizationViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """List, retrieve, and create organizations the user can view."""

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        return orgs_with(self.request.user, Capability.ORG_VIEW)

    def perform_create(self, serializer):
        # A user must never end up with an organization it cannot
        # administer, so the ADMIN membership is created in the same
        # transaction as the organization, not a second request.
        with transaction.atomic():
            organization = serializer.save()
            OrganizationMembership.objects.create(
                organization=organization, user=self.request.user, role=OrganizationRole.ADMIN
            )


class OrganizationMembershipViewSet(
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    List, update (role change), and delete for `OrganizationMembership` rows.
    Creation happens only through `InvitationAcceptView` -- an invitation
    link is the only way a membership row comes into existence for anyone
    but the organization's founding `ADMIN` (see `OrganizationViewSet.perform_create`).

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


class ProjectViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """List, retrieve, and create projects the user can view."""

    queryset = Project.objects.select_related("organization")
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return projects_with(self.request.user, Capability.PROJECT_VIEW)


class ProjectMembershipViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Lists, grants, changes, and revokes `ProjectMembership` roles
    (spec/organization-management: Per-Project and Per-Environment Role
    Grants, tasks 6.6/6.7, 8.2/8.3).

    Creation is authorized entirely by `ProjectMembershipSerializer`'s
    `CapabilityScopedFKMixin`-narrowed `project` field (design D5, Layer 2) --
    DRF has no object on a create, so there is nothing for `HasCapability` to
    check here. Listing is scoped by `PROJECT_VIEW` (task 8.2/8.3) -- ordinary
    visibility, not the `PROJECT_MANAGE_MEMBERS` capability creation requires.

    Update and destroy follow `OrganizationMembershipViewSet`'s split: a
    scoped `get_queryset` (Layer 1 -- a project the requester cannot even see
    is a 404) plus an explicit `_require_manage_permission` check inside the
    mutation (Layer 3 -- visible-but-unprivileged is a 403). Unlike the
    organization case, there is no "never zero admins" invariant to enforce
    at this level, so no row lock is needed here.
    """

    queryset = ProjectMembership.objects.select_related("project__organization", "user")
    serializer_class = ProjectMembershipSerializer

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return ProjectMembershipUpdateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(
            project__in=projects_with(self.request.user, Capability.PROJECT_VIEW)
        )

    def _require_manage_permission(self, membership):
        if not projects_with(self.request.user, Capability.PROJECT_MANAGE_MEMBERS).filter(
            pk=membership.project_id
        ).exists():
            raise PermissionDenied()

    def perform_update(self, serializer):
        self._require_manage_permission(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_manage_permission(instance)
        instance.delete()


class EnvironmentMembershipViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Lists, grants, changes, and revokes `EnvironmentMembership` roles (see
    `ProjectMembershipViewSet`). Listing is scoped by `ENVIRONMENT_VIEW`
    (task 8.2/8.3) -- ordinary visibility, not the `PROJECT_MANAGE_MEMBERS`
    capability creation requires on the environment's parent project.

    Update and destroy are gated by `PROJECT_MANAGE_MEMBERS` on the
    environment's parent project -- there is no separate environment-level
    "manage members" capability, per `EnvironmentMembershipSerializer`.
    """

    queryset = EnvironmentMembership.objects.select_related(
        "environment__project__organization", "user"
    )
    serializer_class = EnvironmentMembershipSerializer

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return EnvironmentMembershipUpdateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(
            environment__in=environments_with(self.request.user, Capability.ENVIRONMENT_VIEW)
        )

    def _require_manage_permission(self, membership):
        if not projects_with(self.request.user, Capability.PROJECT_MANAGE_MEMBERS).filter(
            pk=membership.environment.project_id
        ).exists():
            raise PermissionDenied()

    def perform_update(self, serializer):
        self._require_manage_permission(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_manage_permission(instance)
        instance.delete()


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


class InvitationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Create, list, and revoke single-use organization invitation links.

    Unlike `OrganizationMembershipViewSet`, listing here is scoped by the
    same `org.manage_members` capability creation requires, not by
    `ORG_VIEW` -- an invitation is administration data (who it targets, its
    live link), not ordinary membership visibility, so every action on this
    viewset shares the one gate, all through `get_queryset` (Layer 1: an
    organization the requester cannot manage is a 404, same as an invisible
    one is elsewhere in this app).
    """

    queryset = Invitation.objects.select_related("organization", "created_by", "accepted_by")
    serializer_class = InvitationSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return InvitationCreateSerializer
        return InvitationSerializer

    def get_queryset(self):
        return super().get_queryset().filter(
            organization__in=orgs_with(self.request.user, Capability.ORG_MANAGE_MEMBERS)
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, raw_token = Invitation.issue(
            organization=serializer.validated_data["organization"],
            role=serializer.validated_data["role"],
            created_by=request.user,
        )
        data = InvitationSerializer(invitation).data
        # The one and only place the plain token is ever returned -- it is
        # never stored, and this response is never reachable again.
        data["token"] = raw_token
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        invitation = self.get_object()
        if invitation.revoked_at is None and invitation.accepted_at is None:
            invitation.revoked_at = timezone.now()
            invitation.save(update_fields=["revoked_at"])
        return Response(InvitationSerializer(invitation).data)


class InvitationPreviewView(APIView):
    """
    GET /invitations/{token}/preview/ -- reachable without authentication
    (spec: someone not yet logged in must be able to see what they were
    invited to before registering or logging in).

    Every unusable token -- unknown, expired, revoked, or already accepted --
    answers with the same generic 404. Distinguishing them here would let a
    caller probe which tokens exist (or existed) with no authentication at
    all; `InvitationAcceptView` affords that distinction because reaching it
    already requires holding the link and being logged in.
    """

    permission_classes = [AllowAny]

    def get(self, request, token):
        invitation = Invitation.for_token(token)
        if invitation is None or invitation.is_revoked or invitation.is_accepted or invitation.is_expired:
            raise NotFound("Invitation not found or no longer valid.")
        return Response({"organization_name": invitation.organization.name, "role": invitation.role})


class InvitationAcceptView(APIView):
    """
    POST /invitations/{token}/accept/ -- requires authentication (default
    `IsDashboardUser`). Creates the `OrganizationMembership` for the
    requesting user with the invitation's role, marks the invitation used,
    and enforces the plan's seat limit here -- this is the moment the seat
    is actually consumed, mirroring `OrganizationViewSet.members`.
    """

    def post(self, request, token):
        resolved = Invitation.for_token(token)
        if resolved is None:
            return Response({"error": "invitation_not_found"}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            # select_for_update() serializes this accept against a concurrent
            # one for the same token -- without the row lock, two requests
            # can both observe "not yet accepted" and both commit.
            invitation = Invitation.objects.select_for_update().select_related("organization").get(
                pk=resolved.pk
            )

            if invitation.is_revoked:
                return Response({"error": "invitation_revoked"}, status=status.HTTP_410_GONE)
            if invitation.is_accepted:
                return Response({"error": "invitation_already_used"}, status=status.HTTP_409_CONFLICT)
            if invitation.is_expired:
                return Response({"error": "invitation_expired"}, status=status.HTTP_410_GONE)

            if OrganizationMembership.objects.filter(
                organization=invitation.organization, user=request.user
            ).exists():
                return Response({"error": "already_a_member"}, status=status.HTTP_409_CONFLICT)

            # Same locked seat check as OrganizationViewSet.members: the row
            # lock serializes the count against the insert.
            locked_organization = Organization.objects.select_for_update().get(pk=invitation.organization_id)
            limit = max_seats(locked_organization.plan)
            if limit is not None:
                seat_count = OrganizationMembership.objects.filter(organization=locked_organization).count()
                if seat_count >= limit:
                    return Response({"error": "seat_limit_reached"}, status=status.HTTP_400_BAD_REQUEST)

            membership = OrganizationMembership.objects.create(
                organization=locked_organization, user=request.user, role=invitation.role
            )
            invitation.accepted_by = request.user
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["accepted_by", "accepted_at"])

        return Response(OrganizationMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)
