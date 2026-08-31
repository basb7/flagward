"""
Tests for PATCH/DELETE on /api/v1/tenancy/organizations/{id}/ and
/api/v1/tenancy/projects/{id}/, plus the GET .../deletion_impact/ preview
(spec/organization-management: renaming and deleting tenants).

Delete is the most destructive operation this product has: it requires an
exact `confirm_name` match (the caller must know and type the current name,
not merely flip a boolean), it never bypasses for a superuser, and an
organization delete additionally refuses while other members would lose their
access, all following `OrganizationMembershipViewSet`'s Layer 1 (scoped
`get_queryset`, 404) / Layer 3 (`_require_*_permission`, 403) split.

A caller who only holds a `ProjectMembership` (no `OrganizationMembership` at
all) is an orphaned grant under `tenancy.scoping`'s defence-in-depth check, so
every project-level test below also grants the acting user an
`OrganizationRole.USER` row -- the same convention `test_role_grants.py` uses.
"""
import pytest
from rest_framework.test import APIClient

from core_flags.models import Condition, Environment, FeatureFlag, FlagOverride, StrategyRule
from sdk_api.models import EvaluationLog, SDKRegistration, SDKType
from tenancy.models import (
    EnvironmentMembership,
    Invitation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    Project,
    ProjectMembership,
    ProjectRole,
)


def _make_other_user(username="second-member"):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="tram-quartz-19-belt"
    )


def _build_full_subtree(organization, project, environment, flag, member_user):
    """
    Builds one instance of every cascaded model below `organization`/`project`,
    rooted at the given `flag`/`environment`, plus one project- and one
    environment-membership row for `member_user` and one invitation -- so a
    delete's cascade can be asserted on every model, not just the response
    status.

    `member_user` must hold no `ProjectMembership`/`EnvironmentMembership` on
    `project`/`environment` yet (the unique constraint would collide with the
    acting caller's own grant), so callers pass a user distinct from whoever
    is granted access to perform the request being tested.
    """
    rule = StrategyRule.objects.create(flag=flag, priority=0)
    Condition.objects.create(rule=rule, attribute="country", operator="EQUALS", value="US")
    FlagOverride.objects.create(flag=flag, is_enabled=True, reason="incident")
    EvaluationLog.objects.create(flag=flag, context_hash="abc", result=True)
    SDKRegistration.objects.create(environment=environment, sdk_type=SDKType.PYTHON, version="1.0")
    ProjectMembership.objects.create(project=project, user=member_user, role=ProjectRole.VIEWER)
    EnvironmentMembership.objects.create(environment=environment, user=member_user, role="VIEWER")
    Invitation.issue(organization=organization, role=OrganizationRole.USER, created_by=None)


@pytest.mark.django_db
class TestOrganizationRename:
    def test_org_admin_renames_organization(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/organizations/{organization.id}/", {"name": "Acme Renamed"}, format="json"
        )

        assert response.status_code == 200
        organization.refresh_from_db()
        assert organization.name == "Acme Renamed"

    def test_org_user_without_manage_capability_gets_403(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/organizations/{organization.id}/", {"name": "Hijacked"}, format="json"
        )

        assert response.status_code == 403
        organization.refresh_from_db()
        assert organization.name != "Hijacked"

    def test_cross_tenant_rename_returns_404(self, api_client, user, grant, organization, make_project):
        own_organization = make_project(name="Own", key="own").organization
        grant(user, org=own_organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/organizations/{organization.id}/", {"name": "Planted"}, format="json"
        )

        assert response.status_code == 404
        organization.refresh_from_db()
        assert organization.name != "Planted"


@pytest.mark.django_db
class TestProjectRename:
    def test_project_admin_renames_name_and_key(self, api_client, user, grant, organization, project):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/projects/{project.id}/",
            {"name": "Renamed", "key": "renamed"},
            format="json",
        )

        assert response.status_code == 200
        project.refresh_from_db()
        assert project.name == "Renamed"
        assert project.key == "renamed"

    def test_org_admin_can_also_rename_a_project(self, api_client, user, grant, organization, project):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/projects/{project.id}/", {"name": "Renamed"}, format="json"
        )

        assert response.status_code == 200

    def test_project_editor_without_manage_capability_gets_403(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.EDITOR)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/projects/{project.id}/", {"name": "Hijacked"}, format="json"
        )

        assert response.status_code == 403
        project.refresh_from_db()
        assert project.name != "Hijacked"

    def test_cross_tenant_project_rename_returns_404(
        self, api_client, user, grant, organization, project, make_project
    ):
        own_project = make_project(name="Own", key="own")
        grant(user, org=own_project.organization, role=OrganizationRole.USER)
        grant(user, project=own_project, role=ProjectRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/projects/{project.id}/", {"name": "Planted"}, format="json"
        )

        assert response.status_code == 404
        project.refresh_from_db()
        assert project.name != "Planted"

    def test_project_rename_cannot_change_organization(
        self, api_client, user, grant, organization, project, make_project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        other_organization = make_project(name="Other", key="other").organization
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/projects/{project.id}/",
            {"organization": str(other_organization.id)},
            format="json",
        )

        assert response.status_code == 400
        project.refresh_from_db()
        assert project.organization_id == organization.id

    def test_duplicate_project_key_on_rename_returns_400(
        self, api_client, user, grant, organization, project, make_project
    ):
        sibling = Project.objects.create(organization=organization, name="Sibling", key="sibling")
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/tenancy/projects/{sibling.id}/", {"key": project.key}, format="json"
        )

        assert response.status_code == 400
        sibling.refresh_from_db()
        assert sibling.key == "sibling"


@pytest.mark.django_db
class TestOrganizationDeletionImpact:
    def test_counts_are_accurate(self, api_client, user, grant, organization, project, environment, flag):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        second_project = Project.objects.create(organization=organization, name="Second", key="second")
        second_environment = Environment.objects.create(project=second_project, key="staging", name="Staging")
        FeatureFlag.objects.create(environment=second_environment, key="other-flag", name="Other")
        _build_full_subtree(organization, project, environment, flag, member_user=_make_other_user())
        client = api_client(user)

        response = client.get(f"/api/v1/tenancy/organizations/{organization.id}/deletion_impact/")

        assert response.status_code == 200
        data = response.data
        assert data["projects"] == 2
        assert data["environments"] == 2
        assert data["flags"] == 2
        assert data["strategy_rules"] == 1
        assert data["conditions"] == 1
        assert data["overrides"] == 1
        assert data["evaluation_logs"] == 1
        assert data["sdk_registrations"] == 1
        assert data["organization_memberships"] == 1
        assert data["project_memberships"] == 1
        assert data["environment_memberships"] == 1
        assert data["invitations"] == 1
        assert data["other_members"] == 0

    def test_requires_delete_capability(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.get(f"/api/v1/tenancy/organizations/{organization.id}/deletion_impact/")

        assert response.status_code == 403

    def test_cross_tenant_returns_404(self, api_client, user, grant, organization, make_project):
        own_organization = make_project(name="Own", key="own").organization
        grant(user, org=own_organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.get(f"/api/v1/tenancy/organizations/{organization.id}/deletion_impact/")

        assert response.status_code == 404


@pytest.mark.django_db
class TestProjectDeletionImpact:
    def test_counts_are_accurate(self, api_client, user, grant, organization, project, environment, flag):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        _build_full_subtree(organization, project, environment, flag, member_user=_make_other_user())
        client = api_client(user)

        response = client.get(f"/api/v1/tenancy/projects/{project.id}/deletion_impact/")

        assert response.status_code == 200
        data = response.data
        assert data["environments"] == 1
        assert data["flags"] == 1
        assert data["strategy_rules"] == 1
        assert data["conditions"] == 1
        assert data["overrides"] == 1
        assert data["evaluation_logs"] == 1
        assert data["sdk_registrations"] == 1
        # The acting caller's own ADMIN grant, plus the other member's VIEWER grant.
        assert data["project_memberships"] == 2
        assert data["environment_memberships"] == 1
        assert "organization_memberships" not in data
        assert "other_members" not in data

    def test_requires_delete_capability(self, api_client, user, grant, organization, project):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.EDITOR)
        client = api_client(user)

        response = client.get(f"/api/v1/tenancy/projects/{project.id}/deletion_impact/")

        assert response.status_code == 403

    def test_cross_tenant_returns_404(self, api_client, user, grant, project, make_project):
        own_project = make_project(name="Own", key="own")
        grant(user, org=own_project.organization, role=OrganizationRole.USER)
        grant(user, project=own_project, role=ProjectRole.ADMIN)
        client = api_client(user)

        response = client.get(f"/api/v1/tenancy/projects/{project.id}/deletion_impact/")

        assert response.status_code == 404


@pytest.mark.django_db
class TestOrganizationDelete:
    def test_correct_confirm_name_deletes_and_cascades(
        self, api_client, user, grant, organization, project, environment, flag
    ):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        _build_full_subtree(organization, project, environment, flag, member_user=_make_other_user())
        org_id, project_id, environment_id, flag_id = organization.id, project.id, environment.id, flag.id
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/organizations/{org_id}/",
            {"confirm_name": organization.name},
            format="json",
        )

        assert response.status_code == 204
        assert not Organization.objects.filter(id=org_id).exists()
        assert not Project.objects.filter(id=project_id).exists()
        assert not Environment.objects.filter(id=environment_id).exists()
        assert not FeatureFlag.objects.filter(id=flag_id).exists()
        assert StrategyRule.objects.filter(flag_id=flag_id).count() == 0
        assert Condition.objects.filter(rule__flag_id=flag_id).count() == 0
        assert FlagOverride.objects.filter(flag_id=flag_id).count() == 0
        assert EvaluationLog.objects.filter(flag_id=flag_id).count() == 0
        assert SDKRegistration.objects.filter(environment_id=environment_id).count() == 0
        assert OrganizationMembership.objects.filter(organization_id=org_id).count() == 0
        assert ProjectMembership.objects.filter(project_id=project_id).count() == 0
        assert EnvironmentMembership.objects.filter(environment_id=environment_id).count() == 0
        assert Invitation.objects.filter(organization_id=org_id).count() == 0

    def test_wrong_confirm_name_returns_400_and_deletes_nothing(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/organizations/{organization.id}/",
            {"confirm_name": "Not The Name"},
            format="json",
        )

        assert response.status_code == 400
        assert Organization.objects.filter(id=organization.id).exists()

    def test_missing_confirm_name_returns_400_and_deletes_nothing(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.delete(f"/api/v1/tenancy/organizations/{organization.id}/")

        assert response.status_code == 400
        assert Organization.objects.filter(id=organization.id).exists()

    def test_cross_tenant_delete_returns_404(self, api_client, user, grant, organization, make_project):
        own_organization = make_project(name="Own", key="own").organization
        grant(user, org=own_organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/organizations/{organization.id}/",
            {"confirm_name": organization.name},
            format="json",
        )

        assert response.status_code == 404
        assert Organization.objects.filter(id=organization.id).exists()

    def test_visible_but_unprivileged_delete_returns_403(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/organizations/{organization.id}/",
            {"confirm_name": organization.name},
            format="json",
        )

        assert response.status_code == 403
        assert Organization.objects.filter(id=organization.id).exists()

    def test_delete_blocked_when_other_members_exist(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        other_user = _make_other_user()
        grant(other_user, org=organization, role=OrganizationRole.USER)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/organizations/{organization.id}/",
            {"confirm_name": organization.name},
            format="json",
        )

        assert response.status_code == 400
        assert int(response.data["other_members"]) == 1
        assert Organization.objects.filter(id=organization.id).exists()

    def test_delete_allowed_when_caller_is_sole_member(self, api_client, user, grant, organization):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/organizations/{organization.id}/",
            {"confirm_name": organization.name},
            format="json",
        )

        assert response.status_code == 204
        assert not Organization.objects.filter(id=organization.id).exists()

    def test_delete_allowed_for_callers_only_organization(self, api_client, user, grant, organization):
        """
        Deliberately no "last organization" guard: a user deleting their only
        organization lands back on the empty state that offers to create one.
        """
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        assert OrganizationMembership.objects.filter(user=user).count() == 1
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/organizations/{organization.id}/",
            {"confirm_name": organization.name},
            format="json",
        )

        assert response.status_code == 204


@pytest.mark.django_db
class TestProjectDelete:
    def test_correct_confirm_name_deletes_and_cascades(
        self, api_client, user, grant, organization, project, environment, flag
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        _build_full_subtree(organization, project, environment, flag, member_user=_make_other_user())
        project_id, environment_id, flag_id = project.id, environment.id, flag.id
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/projects/{project_id}/", {"confirm_name": project.name}, format="json"
        )

        assert response.status_code == 204
        assert Organization.objects.filter(id=organization.id).exists()
        assert not Project.objects.filter(id=project_id).exists()
        assert not Environment.objects.filter(id=environment_id).exists()
        assert not FeatureFlag.objects.filter(id=flag_id).exists()
        assert ProjectMembership.objects.filter(project_id=project_id).count() == 0
        assert EnvironmentMembership.objects.filter(environment_id=environment_id).count() == 0

    def test_wrong_confirm_name_returns_400_and_deletes_nothing(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/projects/{project.id}/", {"confirm_name": "Not The Name"}, format="json"
        )

        assert response.status_code == 400
        assert Project.objects.filter(id=project.id).exists()

    def test_cross_tenant_delete_returns_404(self, api_client, user, grant, project, make_project):
        own_project = make_project(name="Own", key="own")
        grant(user, org=own_project.organization, role=OrganizationRole.USER)
        grant(user, project=own_project, role=ProjectRole.ADMIN)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/projects/{project.id}/", {"confirm_name": project.name}, format="json"
        )

        assert response.status_code == 404
        assert Project.objects.filter(id=project.id).exists()

    def test_visible_but_unprivileged_delete_returns_403(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.EDITOR)
        client = api_client(user)

        response = client.delete(
            f"/api/v1/tenancy/projects/{project.id}/", {"confirm_name": project.name}, format="json"
        )

        assert response.status_code == 403
        assert Project.objects.filter(id=project.id).exists()


@pytest.mark.django_db
class TestNoSuperuserBypassOnRenameAndDelete:
    """
    spec/access-control: No Superuser Bypass, extended to rename, delete, and
    deletion_impact for both Organization and Project (see
    `tests.integration.test_tenant_scoping.TestNoSuperuserBypass`).
    """

    def _superuser_without_membership(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_superuser(
            username="root", password="secret", email="root@example.com"
        )

    def test_superuser_cannot_rename_a_foreign_organization(self, organization):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.patch(
            f"/api/v1/tenancy/organizations/{organization.id}/", {"name": "Planted"}, format="json"
        )

        assert response.status_code == 404
        organization.refresh_from_db()
        assert organization.name != "Planted"

    def test_superuser_cannot_view_deletion_impact_of_a_foreign_organization(self, organization):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.get(f"/api/v1/tenancy/organizations/{organization.id}/deletion_impact/")

        assert response.status_code == 404

    def test_superuser_cannot_delete_a_foreign_organization(self, organization):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.delete(
            f"/api/v1/tenancy/organizations/{organization.id}/",
            {"confirm_name": organization.name},
            format="json",
        )

        assert response.status_code == 404
        assert Organization.objects.filter(id=organization.id).exists()

    def test_superuser_cannot_rename_a_foreign_project(self, project):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.patch(
            f"/api/v1/tenancy/projects/{project.id}/", {"name": "Planted"}, format="json"
        )

        assert response.status_code == 404
        project.refresh_from_db()
        assert project.name != "Planted"

    def test_superuser_cannot_view_deletion_impact_of_a_foreign_project(self, project):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.get(f"/api/v1/tenancy/projects/{project.id}/deletion_impact/")

        assert response.status_code == 404

    def test_superuser_cannot_delete_a_foreign_project(self, project):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.delete(
            f"/api/v1/tenancy/projects/{project.id}/", {"confirm_name": project.name}, format="json"
        )

        assert response.status_code == 404
        assert Project.objects.filter(id=project.id).exists()
