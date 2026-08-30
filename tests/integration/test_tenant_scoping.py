"""
Integration tests proving the three enforcement layers actually gate the nine
dashboard viewsets and five narrowed serializer fields (design D5; spec:
access-control, flag-management).

These are the tests design D7 lists as items 9-11: cross-tenant read/write
isolation, the non-`User` principal guard, and the router-coverage sweep.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core_flags.api.serializers import FeatureFlagSerializer
from core_flags.models import Environment, FeatureFlag
from tenancy.models import EnvironmentRole, OrganizationRole, ProjectRole


@pytest.fixture
def tenant_a(make_project, make_environment, make_flag):
    """A project/environment/flag the enforcement tests grant access to."""
    project = make_project(name="Tenant A", key="tenant-a")
    environment = make_environment(project=project, key="prod")
    flag = make_flag(environment=environment, key="checkout")
    return {"project": project, "environment": environment, "flag": flag}


@pytest.fixture
def tenant_b(make_project, make_environment, make_flag):
    """A second, disjoint tenant the enforcement tests never grant access to."""
    project = make_project(name="Tenant B", key="tenant-b")
    environment = make_environment(project=project, key="prod")
    flag = make_flag(environment=environment, key="checkout")
    return {"project": project, "environment": environment, "flag": flag}


@pytest.mark.django_db
class TestCrossTenantIsolation:
    """design D7 test 9: the 404 / 400 / 403 split (task 4.1)."""

    def test_cross_tenant_read_returns_404(self, api_client, user, grant, tenant_a, tenant_b):
        grant(user, environment=tenant_a["environment"], role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.get(f"/api/v1/flags/{tenant_b['flag'].id}/")

        assert response.status_code == 404

    def test_cross_tenant_fk_write_returns_400(self, api_client, user, grant, tenant_a, tenant_b):
        grant(user, org=tenant_a["project"].organization, role=OrganizationRole.USER)
        grant(user, environment=tenant_a["environment"], role=EnvironmentRole.EDITOR)
        client = api_client(user)

        response = client.post(
            "/api/v1/flags/",
            {"environment": str(tenant_b["environment"].id), "key": "new-flag", "name": "New"},
            format="json",
        )

        assert response.status_code == 400
        assert not FeatureFlag.objects.filter(key="new-flag").exists()

    def test_capability_less_write_returns_403(self, api_client, user, grant, tenant_a):
        grant(user, environment=tenant_a["environment"], role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.patch(
            f"/api/v1/flags/{tenant_a['flag'].id}/", {"name": "Renamed"}, format="json"
        )

        assert response.status_code == 403

    def test_list_never_includes_foreign_tenant_rows(
        self, api_client, user, grant, tenant_a, tenant_b
    ):
        grant(user, org=tenant_a["project"].organization, role=OrganizationRole.USER)
        grant(user, environment=tenant_a["environment"], role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.get("/api/v1/flags/")

        assert response.status_code == 200
        returned_ids = {row["id"] for row in response.data["results"]}
        assert str(tenant_a["flag"].id) in returned_ids
        assert str(tenant_b["flag"].id) not in returned_ids


@pytest.mark.django_db
class TestNonUserPrincipalFailsClosed:
    """design D7 test 10 (task 4.2)."""

    def test_x_api_key_on_dashboard_route_returns_403(self, environment):
        client = APIClient()

        response = client.get("/api/v1/flags/", HTTP_X_API_KEY=environment.api_key)

        # A bare 403 (and not a 500) is the whole proof: an unhandled
        # AttributeError on the Environment principal would surface as an
        # uncaught exception here, not a clean status code.
        assert response.status_code == 403

    def test_sdk_endpoints_are_unaffected_by_the_global_default(self, environment):
        client = APIClient()

        response = client.get("/api/v1/sdk/flags/", HTTP_X_API_KEY=environment.api_key)

        assert response.status_code == 200


@pytest.mark.django_db
class TestRouterCoverage:
    """design D7 test 11 (task 4.3)."""

    def test_every_registered_viewset_is_tenant_scoped(self):
        import tenancy.permissions as permissions_module
        from core_flags.api.urls import router as core_router
        from sdk_api.api.urls import router as sdk_router
        from tenancy.permissions import TenantScopedViewSetMixin

        routers = (core_router, sdk_router)
        checked = 0
        for router in routers:
            for _prefix, viewset, _basename in router.registry:
                checked += 1
                assert issubclass(viewset, TenantScopedViewSetMixin), (
                    f"{viewset.__name__} does not subclass TenantScopedViewSetMixin"
                )
                assert viewset.environment_lookup is not permissions_module._UNSET, (
                    f"{viewset.__name__} left environment_lookup unset"
                )

        assert checked == 7, "expected the 5 core_flags + 2 sdk_api viewsets"


@pytest.mark.django_db
class TestEnvironmentSerializerProjectNarrowed:
    """spec: Root-level cross-tenant write (F3); tasks 4.9-4.11."""

    def test_foreign_project_rejected_on_create(
        self, api_client, user, grant, organization, project, make_project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        foreign_project = make_project(name="Foreign", key="foreign")
        client = api_client(user)

        response = client.post(
            "/api/v1/environments/",
            {"name": "Prod", "key": "prod", "project": str(foreign_project.id)},
            format="json",
        )

        assert response.status_code == 400
        assert not Environment.objects.filter(project=foreign_project).exists()

    def test_own_project_accepted_on_create(self, api_client, user, grant, organization, project):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        client = api_client(user)

        response = client.post(
            "/api/v1/environments/",
            {"name": "Prod", "key": "prod", "project": str(project.id)},
            format="json",
        )

        assert response.status_code == 201
        assert Environment.objects.filter(project=project, key="prod").exists()

    def test_move_environment_to_foreign_project_rejected(
        self, api_client, user, grant, organization, environment, make_project
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, environment=environment, role=EnvironmentRole.ADMIN)
        foreign_project = make_project(name="Foreign", key="foreign")
        client = api_client(user)

        response = client.patch(
            f"/api/v1/environments/{environment.id}/",
            {"project": str(foreign_project.id)},
            format="json",
        )

        assert response.status_code == 400
        environment.refresh_from_db()
        assert environment.project != foreign_project

    def test_create_payload_without_project_is_rejected(self, api_client, user, grant, project):
        """
        Task 8.1 -- pins the exact contract the dashboard caller violated:
        `environmentsApi.create` sent only `{name, key}` with no `project` at
        all, so every environment creation from the UI has 400'd since this
        field became required (F3/slice 4). This is the literal payload shape
        the frontend was sending; `test_foreign_project_rejected_on_create`
        above covers a *present-but-foreign* project, not an *absent* one.
        """
        grant(user, org=project.organization, role=OrganizationRole.USER)
        grant(user, project=project, role=ProjectRole.ADMIN)
        client = api_client(user)

        response = client.post(
            "/api/v1/environments/",
            {"name": "Prod", "key": "prod"},
            format="json",
        )

        assert response.status_code == 400
        assert "project" in response.data
        assert not Environment.objects.filter(key="prod").exists()


@pytest.mark.django_db
class TestSerializerWithoutRequestContext:
    """design's `.none()` decision (D5); task 4.12."""

    def test_write_without_request_context_is_rejected(self, environment):
        serializer = FeatureFlagSerializer(
            data={"environment": str(environment.id), "key": "flag", "name": "Flag"}
        )

        assert serializer.is_valid() is False
        assert "environment" in serializer.errors

    def test_read_without_request_context_still_serializes(self, flag):
        serializer = FeatureFlagSerializer(flag)

        assert serializer.data["id"] == str(flag.id)
        # PrimaryKeyRelatedField.to_representation returns the raw pk, not a
        # stringified one -- it never consults the (possibly `.none()`d)
        # queryset, which is exactly what keeps reads working without a
        # request in context.
        assert serializer.data["environment"] == flag.environment.id


@pytest.mark.django_db
class TestProjectQueryParamFilter:
    """
    design D10, task 8.4/8.5: `?project=` on `GET /api/v1/environments/` and
    `/api/v1/flags/`. Both tenants are made VISIBLE to the same user so this
    test proves the filter itself narrows the response -- Layer 1 tenant
    scoping alone would already return both without it.
    """

    def test_environments_filtered_by_project(self, api_client, user, grant, tenant_a, tenant_b):
        grant(user, org=tenant_a["project"].organization, role=OrganizationRole.USER)
        grant(user, org=tenant_b["project"].organization, role=OrganizationRole.USER)
        grant(user, environment=tenant_a["environment"], role=EnvironmentRole.VIEWER)
        grant(user, environment=tenant_b["environment"], role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.get(f"/api/v1/environments/?project={tenant_a['project'].id}")

        assert response.status_code == 200
        ids = {row["id"] for row in response.data["results"]}
        assert ids == {str(tenant_a["environment"].id)}

    def test_flags_filtered_by_project(self, api_client, user, grant, tenant_a, tenant_b):
        grant(user, org=tenant_a["project"].organization, role=OrganizationRole.USER)
        grant(user, org=tenant_b["project"].organization, role=OrganizationRole.USER)
        grant(user, environment=tenant_a["environment"], role=EnvironmentRole.VIEWER)
        grant(user, environment=tenant_b["environment"], role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.get(f"/api/v1/flags/?project={tenant_a['project'].id}")

        assert response.status_code == 200
        ids = {row["id"] for row in response.data["results"]}
        assert ids == {str(tenant_a["flag"].id)}

    def test_environments_malformed_project_returns_400(self, api_client, user, grant, tenant_a):
        grant(user, environment=tenant_a["environment"], role=EnvironmentRole.VIEWER)
        client = api_client(user)

        response = client.get("/api/v1/environments/?project=not-a-uuid")

        assert response.status_code == 400


@pytest.mark.django_db
class TestNoSuperuserBypass:
    """
    spec/access-control: No Superuser Bypass.

    The superadmin is an operations role exercised through Django admin, not a
    product role. The dashboard API stays scoped by membership with no
    exceptions, because every exception is one more path to get wrong.

    That guarantee currently rests on the absence of a line: no
    `is_superuser` check exists anywhere in `tenancy/permissions.py`. Absence
    is not something a reader notices, and it is not something a reviewer can
    be relied on to keep noticing -- one plausible "unblock the admin" commit
    reintroduces it silently. These tests fail the moment it comes back.
    """

    def _superuser_without_membership(self):
        """A Django superuser holding no membership anywhere."""
        return get_user_model().objects.create_superuser(
            username="root", password="secret", email="root@example.com"
        )

    def test_superuser_sees_no_foreign_flags(self, environment):
        FeatureFlag.objects.create(environment=environment, key="secret", name="Secret")
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.get("/api/v1/flags/")

        assert response.status_code == 200
        assert response.data["results"] == []

    def test_superuser_cannot_retrieve_a_foreign_flag(self, flag):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.get(f"/api/v1/flags/{flag.id}/")

        assert response.status_code == 404

    def test_superuser_cannot_write_into_a_foreign_environment(self, environment):
        """
        403, not 400: holding no membership anywhere, the superuser has
        `flag.edit` nowhere, so Layer 3 denies before Layer 2's narrowed FK
        is ever consulted. The 400 belongs to a caller who *does* hold the
        capability somewhere and aims it at a foreign parent -- that is
        `test_cross_tenant_fk_write_returns_400`. What matters here is that
        both layers refuse, and neither consults `is_superuser`.
        """
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.post(
            "/api/v1/flags/",
            {"environment": str(environment.id), "key": "planted", "name": "Planted"},
            format="json",
        )

        assert response.status_code == 403
        assert not FeatureFlag.objects.filter(key="planted").exists()

    def test_superuser_sees_no_foreign_analytics(self, environment):
        client = APIClient()
        client.force_authenticate(user=self._superuser_without_membership())

        response = client.get("/api/v1/analytics/overview/")

        assert response.status_code == 200
        assert response.data["environments"]["total"] == 0
