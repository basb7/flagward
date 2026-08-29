"""
Serializers for the tenancy API.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from tenancy.models import Organization, OrganizationMembership, OrganizationRole, Project

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
