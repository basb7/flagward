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
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core_flags.models import Condition, Environment, FeatureFlag, FlagOverride, StrategyRule
from sdk_api.models import EvaluationLog, SDKRegistration
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


def _require_confirm_name(request, instance):
    """
    Delete is the most destructive operation this product has, so a boolean
    flag is not enough -- it is something a client sets once and forgets,
    protecting nobody. The caller must instead supply the object's exact
    current `name` back (GitHub's "type the repository name" pattern), which
    cannot be satisfied by accident.
    """
    confirm_name = request.data.get("confirm_name")
    if confirm_name != instance.name:
        raise ValidationError(
            {"confirm_name": "confirm_name does not match the current name; nothing was deleted."}
        )


def _organization_deletion_impact(organization, requesting_user):
    """Per-subtree counts below `organization`, for a pre-delete impact preview."""
    organization_memberships = OrganizationMembership.objects.filter(organization=organization)
    return {
        "projects": Project.objects.filter(organization=organization).count(),
        "environments": Environment.objects.filter(project__organization=organization).count(),
        "flags": FeatureFlag.objects.filter(environment__project__organization=organization).count(),
        "strategy_rules": StrategyRule.objects.filter(
            flag__environment__project__organization=organization
        ).count(),
        "conditions": Condition.objects.filter(
            rule__flag__environment__project__organization=organization
        ).count(),
        "overrides": FlagOverride.objects.filter(
            flag__environment__project__organization=organization
        ).count(),
        "evaluation_logs": EvaluationLog.objects.filter(
            flag__environment__project__organization=organization
        ).count(),
        "sdk_registrations": SDKRegistration.objects.filter(
            environment__project__organization=organization
        ).count(),
        "organization_memberships": organization_memberships.count(),
        "project_memberships": ProjectMembership.objects.filter(
            project__organization=organization
        ).count(),
        "environment_memberships": EnvironmentMembership.objects.filter(
            environment__project__organization=organization
        ).count(),
        "invitations": Invitation.objects.filter(organization=organization).count(),
        "other_members": organization_memberships.exclude(user=requesting_user).count(),
    }


def _project_deletion_impact(project):
    """Per-subtree counts below `project`, for a pre-delete impact preview."""
    return {
        "environments": Environment.objects.filter(project=project).count(),
        "flags": FeatureFlag.objects.filter(environment__project=project).count(),
        "strategy_rules": StrategyRule.objects.filter(flag__environment__project=project).count(),
        "conditions": Condition.objects.filter(rule__flag__environment__project=project).count(),
        "overrides": FlagOverride.objects.filter(flag__environment__project=project).count(),
        "evaluation_logs": EvaluationLog.objects.filter(flag__environment__project=project).count(),
        "sdk_registrations": SDKRegistration.objects.filter(environment__project=project).count(),
        "project_memberships": ProjectMembership.objects.filter(project=project).count(),
        "environment_memberships": EnvironmentMembership.objects.filter(
            environment__project=project
        ).count(),
    }


class OrganizationViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """List, retrieve, create, rename, and delete organizations the user can view."""

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

    def _require_manage_permission(self, organization):
        # Layer 3: visible-but-unprivileged is a 403, same split as
        # `OrganizationMembershipViewSet`.
        if not orgs_with(self.request.user, Capability.ORG_MANAGE).filter(pk=organization.pk).exists():
            raise PermissionDenied()

    def _require_delete_permission(self, organization):
        if not orgs_with(self.request.user, Capability.ORG_DELETE).filter(pk=organization.pk).exists():
            raise PermissionDenied()

    def perform_update(self, serializer):
        self._require_manage_permission(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_delete_permission(instance)
        _require_confirm_name(self.request, instance)
        # An organization with other members takes their access and their
        # data with it, with no consent from them -- blocked rather than
        # merely reported, since this app has no other way to hand off or
        # preserve their access first. Remove the other members through
        # OrganizationMembershipViewSet before deleting, a deliberate speed
        # bump on the single most destructive operation this product has.
        # Deleting the caller's own only organization is deliberately left
        # unguarded here: it is not destructive to anyone but the caller, who
        # lands back on the empty state offering to create one.
        other_members = (
            OrganizationMembership.objects.filter(organization=instance)
            .exclude(user=self.request.user)
            .count()
        )
        if other_members > 0:
            raise ValidationError(
                {
                    "error": "organization_has_other_members",
                    "other_members": other_members,
                    "detail": (
                        f"This organization has {other_members} other member(s); "
                        "remove them first before deleting it."
                    ),
                }
            )
        instance.delete()

    @action(detail=True, methods=["get"])
    def deletion_impact(self, request, pk=None):
        """
        Counts of everything a delete would remove, so a caller can decide
        before it happens instead of after. Gated by the same capability as
        delete itself -- its only purpose is informing that decision.
        """
        organization = self.get_object()
        self._require_delete_permission(organization)
        return Response(_organization_deletion_impact(organization, request.user))


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


class ProjectViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """List, retrieve, create, rename, and delete projects the user can view."""

    queryset = Project.objects.select_related("organization")
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return projects_with(self.request.user, Capability.PROJECT_VIEW)

    def _require_manage_permission(self, project):
        # Layer 3: visible-but-unprivileged is a 403, same split as
        # `OrganizationViewSet`/`ProjectMembershipViewSet`.
        if not projects_with(self.request.user, Capability.PROJECT_MANAGE).filter(pk=project.pk).exists():
            raise PermissionDenied()

    def _require_delete_permission(self, project):
        if not projects_with(self.request.user, Capability.PROJECT_DELETE).filter(pk=project.pk).exists():
            raise PermissionDenied()

    def perform_update(self, serializer):
        self._require_manage_permission(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_delete_permission(instance)
        _require_confirm_name(self.request, instance)
        # Unlike organization delete, there is no membership-blocking rule
        # here: project members remain members of the organization and keep
        # access to its other projects, a strictly smaller blast radius.
        instance.delete()

    @action(detail=True, methods=["get"])
    def deletion_impact(self, request, pk=None):
        """See `OrganizationViewSet.deletion_impact` -- same shape, one level down."""
        project = self.get_object()
        self._require_delete_permission(project)
        return Response(_project_deletion_impact(project))


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
        # A clickable link built the same way the password-reset email
        # builds its own -- the admin used to get the bare token back and
        # had to assemble `/invite/<token>` by hand, matching the frontend
        # route at frontend/src/app/invite/[token].
        # `.rstrip("/")` here too, not just in config.settings.env_base_url:
        # a value set directly on `settings` (tests, another override) may
        # not have gone through that helper, and a doubled slash must not
        # depend on it.
        data["link"] = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/invite/{raw_token}"
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
