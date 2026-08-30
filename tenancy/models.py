"""
Tenancy models: the Organization/Project/Environment hierarchy and the three
role-based membership tables that grant access at each level.
"""
import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver


class Plan(models.TextChoices):
    """Subscription plan, controlling an organization's seat ceiling."""
    COMMUNITY = "COMMUNITY", "Community"
    STARTER = "STARTER", "Starter"
    TEAM = "TEAM", "Team"


class OrganizationRole(models.TextChoices):
    """
    Roles at the organization level.

    ADMIN is a full key to the account, not a day-to-day administration role:
    it can delete the organization, and every project, environment and flag
    cascades with it. There is deliberately no role between ADMIN and VIEWER —
    an earlier OWNER role granted exactly what ADMIN grants, and a role that
    distinguishes nothing can only mislead whoever assigns it.

    USER is a plain member. It grants only ORG_VIEW -- enough to know which
    organization you belong to and navigate into it -- and says nothing about
    the projects inside, which arrive through project and environment grants
    or not at all. It is named USER rather than VIEWER because "viewer" at
    this level reads as "can view what the organization contains", which is
    the opposite of what it means.
    """
    ADMIN = "ADMIN", "Admin"
    USER = "USER", "User"


class ProjectRole(models.TextChoices):
    """Roles at the project level."""
    ADMIN = "ADMIN", "Admin"
    EDITOR = "EDITOR", "Editor"
    OPERATOR = "OPERATOR", "Operator"
    VIEWER = "VIEWER", "Viewer"


class EnvironmentRole(models.TextChoices):
    """Roles at the environment level."""
    ADMIN = "ADMIN", "Admin"
    EDITOR = "EDITOR", "Editor"
    OPERATOR = "OPERATOR", "Operator"
    VIEWER = "VIEWER", "Viewer"


class Organization(models.Model):
    """The top of the tenancy hierarchy."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.COMMUNITY)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Project(models.Model):
    """A project groups environments inside one organization."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=255)
    key = models.SlugField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key"],
                name="unique_project_key_per_organization",
            ),
        ]

    def __str__(self):
        return f"{self.organization.name}/{self.key}"


class OrganizationMembership(models.Model):
    """A user's role inside one organization."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_memberships"
    )
    role = models.CharField(max_length=20, choices=OrganizationRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="unique_organization_membership"
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=OrganizationRole.values),
                name="orgmembership_role_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="orgmembership_user_idx"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"


class ProjectMembership(models.Model):
    """A user's role inside one project."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships"
    )
    role = models.CharField(max_length=20, choices=ProjectRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="unique_project_membership"),
            models.CheckConstraint(
                condition=models.Q(role__in=ProjectRole.values),
                name="projectmembership_role_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="projectmembership_user_idx"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.project} ({self.role})"


class EnvironmentMembership(models.Model):
    """A user's role inside one environment."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        "core_flags.Environment", on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="environment_memberships"
    )
    role = models.CharField(max_length=20, choices=EnvironmentRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["environment", "user"], name="unique_environment_membership"
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=EnvironmentRole.values),
                name="envmembership_role_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="envmembership_user_idx"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.environment} ({self.role})"


@receiver(post_delete, sender=OrganizationMembership)
def _revoke_grants_scoped_to_the_removed_organization(sender, instance, **kwargs):
    """
    Removal cascade (slice 6b's Layer 1): losing an `OrganizationMembership`
    must also lose every `ProjectMembership`/`EnvironmentMembership` the same
    user holds *inside that organization* -- otherwise a project or
    environment grant outlives the membership that justified it, and keeps
    working.

    This is a `post_delete` signal on the model, not an override of
    `OrganizationMembership.delete()` and not logic living in the DRF view,
    because `QuerySet.delete()` (what Django admin's "Delete selected" bulk
    action uses) never calls a model's `delete()` -- an override would only
    catch the single-object path (the API view, `instance.delete()` in a
    script) and leave the admin's bulk action, and any future bulk deletion
    written the same way, free to reopen this exact hole. A `post_delete`
    signal is dispatched by Django's `Collector` for every row it deletes,
    single or bulk alike -- and registering a receiver here also disables
    the "fast delete" SQL optimisation for this model, so the collector is
    guaranteed to fetch full instances and fire this signal once per row
    rather than issuing one bare `DELETE ... WHERE pk IN (...)` with no
    signal at all.

    Scoped to `instance.organization_id`: grants in the user's *other*
    organizations are untouched. Wrapped in its own `transaction.atomic()`
    so the cascade is all-or-nothing regardless of whether the caller (a
    view, the admin, a script) already opened a transaction of its own --
    nested atomic blocks are just savepoints.
    """
    with transaction.atomic():
        ProjectMembership.objects.filter(
            user_id=instance.user_id, project__organization_id=instance.organization_id
        ).delete()
        EnvironmentMembership.objects.filter(
            user_id=instance.user_id,
            environment__project__organization_id=instance.organization_id,
        ).delete()
