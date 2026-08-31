"""
Serializers for the tenancy API.
"""
from rest_framework import serializers

from tenancy.capabilities import Capability
from tenancy.models import (
    EnvironmentMembership,
    EnvironmentRole,
    Invitation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    Project,
    ProjectMembership,
    ProjectRole,
)
from tenancy.scoping import environments_with, orgs_with, projects_with
from tenancy.serializers import CapabilityScopedFKMixin


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""
    class Meta:
        model = Organization
        fields = ['id', 'name', 'plan', 'created_at']
        read_only_fields = ['id', 'plan', 'created_at']


class ProjectSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """
    Serializer for Project model.

    `organization` is narrowed (design D5, Layer 2 -- the only create-time
    gate) to organizations the requester holds `project.create` on. This is
    the root of the FK-narrowing chain one level above `EnvironmentSerializer`'s
    `project` field -- without it, any authenticated user could POST a
    project into another organization's account by UUID.
    """
    capability_scoped_fields = {
        "organization": (Capability.PROJECT_CREATE, orgs_with),
    }

    class Meta:
        model = Project
        fields = ['id', 'organization', 'name', 'key', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        # A rename must never double as a move-between-orgs primitive: moving
        # a project changes whose capabilities govern its whole subtree, a
        # different and far riskier operation than renaming it.
        if self.instance is not None and "organization" in self.initial_data:
            raise serializers.ValidationError(
                {"organization": "organization is immutable; create a new project instead of moving this one."}
            )
        return attrs


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    """
    Read-only representation of a membership row. `organization` and `user`
    stay read-only here -- both are supplied by the view from the URL and the
    creation payload, never as writable FKs on this serializer, so no
    `CapabilityScopedFKMixin` narrowing is needed for this shape.
    """
    # The screen listing these rows has to name people, and a bare `user` pk
    # names nobody. Read-only, sourced from the already-related user, and no
    # wider than the row itself: seeing the username of someone in an
    # organization you can already list is the point of a members screen.
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ['id', 'organization', 'user', 'username', 'role', 'created_at']
        read_only_fields = fields


class OrganizationMembershipUpdateSerializer(serializers.ModelSerializer):
    """
    Role-only update for an existing `OrganizationMembership` (tasks 6.8/6.9:
    the Organization Administration Invariant is enforced by the view, not
    here -- the check needs `select_for_update()` inside one transaction,
    which a serializer cannot express).
    """
    class Meta:
        model = OrganizationMembership
        fields = ['id', 'organization', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'organization', 'user', 'created_at']


class ProjectMembershipSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """
    Grants a `ProjectMembership` role to a user (spec/organization-management:
    Per-Project and Per-Environment Role Grants).

    `project` is narrowed (design D5, Layer 2 -- the only create-time gate)
    to projects the requester holds `project.manage_members` on. The target
    `user` is left unnarrowed on purpose -- the organization-membership
    prerequisite is a cross-field check (`validate`), not a queryset filter,
    because it depends on the *chosen* project's organization.
    """
    capability_scoped_fields = {
        "project": (Capability.PROJECT_MANAGE_MEMBERS, projects_with),
    }

    # The screen listing these rows has to name people, and a bare `user` pk
    # names nobody. Read-only, sourced from the already-related user, and no
    # wider than the row itself: seeing the username of someone in an
    # organization you can already list is the point of a members screen.
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ['id', 'project', 'user', 'username', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        project = attrs["project"]
        target_user = attrs["user"]
        if not OrganizationMembership.objects.filter(
            organization=project.organization, user=target_user
        ).exists():
            raise serializers.ValidationError(
                "Target user has no organization membership in this organization."
            )
        return attrs


class ProjectMembershipUpdateSerializer(serializers.ModelSerializer):
    """
    Role-only update for an existing `ProjectMembership` -- `project` and
    `user` stay read-only, same split as `OrganizationMembershipUpdateSerializer`:
    changing who a grant applies to is a new grant, not an edit of this one.
    """
    class Meta:
        model = ProjectMembership
        fields = ['id', 'project', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'project', 'user', 'created_at']


class EnvironmentMembershipSerializer(CapabilityScopedFKMixin, serializers.ModelSerializer):
    """
    Grants an `EnvironmentMembership` role to a user
    (spec/organization-management: Per-Project and Per-Environment Role
    Grants). Gated by `project.manage_members` on the environment's parent
    project, per the spec's requirement text -- there is no separate
    environment-level "manage members" capability.
    """
    capability_scoped_fields = {
        "environment": (Capability.PROJECT_MANAGE_MEMBERS, environments_with),
    }

    # The screen listing these rows has to name people, and a bare `user` pk
    # names nobody. Read-only, sourced from the already-related user, and no
    # wider than the row itself: seeing the username of someone in an
    # organization you can already list is the point of a members screen.
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = EnvironmentMembership
        fields = ['id', 'environment', 'user', 'username', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        environment = attrs["environment"]
        target_user = attrs["user"]
        if not OrganizationMembership.objects.filter(
            organization=environment.project.organization, user=target_user
        ).exists():
            raise serializers.ValidationError(
                "Target user has no organization membership in this organization."
            )
        return attrs


class EnvironmentMembershipUpdateSerializer(serializers.ModelSerializer):
    """
    Role-only update for an existing `EnvironmentMembership` -- same split as
    `ProjectMembershipUpdateSerializer`: `environment` and `user` stay
    read-only.
    """
    class Meta:
        model = EnvironmentMembership
        fields = ['id', 'environment', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'environment', 'user', 'created_at']


class EffectiveCapabilitiesPreviewSerializer(CapabilityScopedFKMixin, serializers.Serializer):
    """
    Input for `POST /effective-capabilities/preview/` (design D10). Takes
    PROPOSED, unsaved roles -- nothing here is persisted.

    `organization` is narrowed (design D5, Layer 2) to organizations the
    requester can see, exactly like every other writable FK in this app --
    without it, an invisible organization id would 400 differently from a
    visible one, a small but real existence oracle for something meant to be
    unprobable by a caller who cannot administer it.
    """
    capability_scoped_fields = {
        "organization": (Capability.ORG_VIEW, orgs_with),
    }

    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    organization_role = serializers.ChoiceField(
        choices=OrganizationRole.choices, required=False, allow_null=True, default=None
    )
    project_roles = serializers.DictField(
        child=serializers.ChoiceField(choices=ProjectRole.choices), required=False, default=dict
    )
    environment_roles = serializers.DictField(
        child=serializers.ChoiceField(choices=EnvironmentRole.choices), required=False, default=dict
    )


class InvitationSerializer(serializers.ModelSerializer):
    """
    Read-only representation of an invitation row (list/create/revoke
    responses). The raw token is never one of these fields -- it is handed
    back exactly once, by the create view, alongside this same shape.
    """
    created_by_username = serializers.SerializerMethodField()
    accepted_by_username = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = [
            'id', 'organization', 'role', 'created_by', 'created_by_username',
            'expires_at', 'accepted_by', 'accepted_by_username', 'accepted_at',
            'revoked_at', 'created_at', 'status',
        ]
        read_only_fields = fields

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by_id else None

    def get_accepted_by_username(self, obj):
        return obj.accepted_by.username if obj.accepted_by_id else None

    def get_status(self, obj):
        if obj.is_accepted:
            return "accepted"
        if obj.is_revoked:
            return "revoked"
        if obj.is_expired:
            return "expired"
        return "pending"


class InvitationCreateSerializer(CapabilityScopedFKMixin, serializers.Serializer):
    """
    Input for `POST /invitations/` (an admin creates a single-use invitation
    link). `organization` is narrowed (design D5, Layer 2 -- the only
    create-time gate) to organizations the requester holds
    `org.manage_members` on, same narrowing pattern as every other writable
    FK in this app.
    """
    capability_scoped_fields = {
        "organization": (Capability.ORG_MANAGE_MEMBERS, orgs_with),
    }

    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    role = serializers.ChoiceField(choices=OrganizationRole.choices)
