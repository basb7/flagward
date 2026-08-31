"""
Tests for POST /api/v1/tenancy/effective-capabilities/preview/ (design D10:
the effective-capability preview, mitigating the top risk of admins
misreading union/carve-out role composition). Answers through
`resolve_capabilities` -- the same pure function enforcement uses -- so this
test also asserts the preview can never disagree with what is actually
enforced (task 6.10).
"""
import pytest
from django.contrib.auth import get_user_model

from tenancy.capabilities import resolve_capabilities
from tenancy.models import EnvironmentRole, Organization, OrganizationRole, ProjectRole
from tenancy.scoping import capabilities_for

User = get_user_model()


@pytest.mark.django_db
class TestEffectiveCapabilitiesPreview:
    def test_preview_matches_resolve_capabilities(
        self, api_client, user, grant, organization, project, environment
    ):
        """The preview's answer for one environment matches resolve_capabilities directly."""
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/effective-capabilities/preview/",
            {
                "organization": str(project.organization_id),
                "organization_role": None,
                "project_roles": {},
                "environment_roles": {str(environment.id): EnvironmentRole.OPERATOR},
            },
            format="json",
        )

        assert response.status_code == 200
        expected = sorted(resolve_capabilities(None, None, EnvironmentRole.OPERATOR))
        assert response.data["environments"] == [
            {"id": str(environment.id), "key": environment.key, "capabilities": expected}
        ]

    def test_preview_never_disagrees_with_enforcement(
        self, api_client, user, grant, organization, project, environment
    ):
        """
        Grant the SAME roles the preview was asked about, then compare the
        preview's answer against `capabilities_for` -- the function
        enforcement actually calls. They must be identical, because the
        preview answers through `resolve_capabilities` and nothing else.
        """
        grant(user, org=organization, role=OrganizationRole.ADMIN)  # to call the preview
        target_user = User.objects.create_user(username="target", email="target@example.com", password="secret")
        grant(target_user, org=organization, role=OrganizationRole.USER)
        grant(target_user, project=project, role=ProjectRole.VIEWER)
        grant(target_user, environment=environment, role=EnvironmentRole.EDITOR)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/effective-capabilities/preview/",
            {
                "organization": str(organization.id),
                "organization_role": OrganizationRole.USER,
                "project_roles": {str(project.id): ProjectRole.VIEWER},
                "environment_roles": {str(environment.id): EnvironmentRole.EDITOR},
            },
            format="json",
        )

        assert response.status_code == 200
        previewed = set(response.data["environments"][0]["capabilities"])
        enforced = capabilities_for(target_user, environment)
        assert previewed == enforced

    def test_preview_rejects_without_manage_members_on_referenced_project(
        self, api_client, user, grant, organization, project, environment
    ):
        """A caller with no `project.manage_members` on the referenced project is refused."""
        grant(user, org=organization, role=OrganizationRole.USER)  # org-visible, not project-privileged
        grant(user, project=project, role=ProjectRole.VIEWER)
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/effective-capabilities/preview/",
            {
                "organization": str(project.organization_id),
                "environment_roles": {str(environment.id): EnvironmentRole.OPERATOR},
            },
            format="json",
        )

        assert response.status_code == 403

    def test_preview_rejects_foreign_organization(self, api_client, user):
        """An organization the caller cannot even see must not be previewable."""
        foreign_org = Organization.objects.create(name="Foreign", plan="COMMUNITY")
        client = api_client(user)

        response = client.post(
            "/api/v1/tenancy/effective-capabilities/preview/",
            {"organization": str(foreign_org.id)},
            format="json",
        )

        assert response.status_code == 400
