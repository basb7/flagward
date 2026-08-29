"""
Serializers for the tenancy API.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from tenancy.capabilities import Capability
from tenancy.models import (
    EnvironmentMembership,
    EnvironmentRole,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    Project,
    ProjectMembership,
    ProjectRole,
)
from tenancy.scoping import environments_with, orgs_with, projects_with
from tenancy.serializers import CapabilityScopedFKMixin

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""
    class Meta:
        model = Organization
        fields = ['id', 'name', 'plan', 'created_at']
        read_only_fields = ['id', 'plan', 'created_at']


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model."""
    class Meta:
        model = Project
        fields = ['id', 'organization', 'name', 'key', 'created_at']
        read_only_fields = ['id', 'organization', 'created_at']


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    """
    Read-only representation of a membership row. `organization` and `user`
    stay read-only here -- both are supplied by the view from the URL and the
    creation payload, never as writable FKs on this serializer, so no
    `CapabilityScopedFKMixin` narrowing is needed for this shape.
    """
    class Meta:
        model = OrganizationMembership
        fields = ['id', 'organization', 'user', 'role', 'created_at']
        read_only_fields = fields


class OrganizationMemberCreateSerializer(serializers.Serializer):
    """
    Input for `POST /organizations/{id}/members/` (spec/organization-management:
    An Admin Creates and Attaches Users). Creates a brand-new `auth.User`, not
    an invitation of an existing one -- the requirement is explicit that this
    endpoint both creates the account and attaches it.
    """
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=OrganizationRole.choices)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value


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

    class Meta:
        model = ProjectMembership
        fields = ['id', 'project', 'user', 'role', 'created_at']
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

    class Meta:
        model = EnvironmentMembership
        fields = ['id', 'environment', 'user', 'role', 'created_at']
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
