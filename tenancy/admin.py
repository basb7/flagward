"""
Tenancy admin configuration.
"""
from django.contrib import admin

from .models import (
    EnvironmentMembership,
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "created_at")
    search_fields = ("name",)
    list_filter = ("plan",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "organization", "created_at")
    search_fields = ("name", "key")
    list_filter = ("organization",)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    list_filter = ("role", "organization")
    search_fields = ("user__username", "organization__name")


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "role", "created_at")
    list_filter = ("role", "project")
    search_fields = ("user__username", "project__name")


@admin.register(EnvironmentMembership)
class EnvironmentMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "environment", "role", "created_at")
    list_filter = ("role", "environment")
    search_fields = ("user__username", "environment__name")
