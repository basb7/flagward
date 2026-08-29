"""
Serializers for the tenancy API.
"""
from rest_framework import serializers

from tenancy.models import Organization, Project


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
