"""
Tests for `Project.key` and `Environment.key` being derived from `name`
(POST /api/v1/tenancy/projects/ and POST /api/v1/environments/).

Neither key resolves anything -- no URL, filter, lookup or SDK path reads
them; the SDK authenticates with `Environment.api_key` and everything else
addresses rows by UUID. Asking a human to invent one at create time bought
nothing, so the server derives it. It stays writable afterwards because the
rename dialogs edit it, and it is never re-derived on update: a key that
changes under you while you rename something is worse than one you typed.
"""
from unittest.mock import patch

import pytest
from django.db import IntegrityError

from core_flags.models import Environment
from tenancy.models import (
    EnvironmentRole,
    OrganizationRole,
    Project,
    ProjectRole,
)
from tenancy.slugs import DERIVED_KEY_MAX_ATTEMPTS

PROJECTS_URL = "/api/v1/tenancy/projects/"
ENVIRONMENTS_URL = "/api/v1/environments/"


def flaky_save(model, *, failures):
    """
    Replacement for `model.save` that raises `IntegrityError` on its first
    `failures` calls and then saves for real, recording the key each attempt
    carried.

    This is how the race gets simulated deterministically: a real concurrent
    create loses at the database, and what the loser must do is come back
    with a *different* key. Threads would prove the same thing far less
    reliably, so the constraint violation is injected instead and the
    recorded keys are what the assertions read.
    """
    real_save = model.save
    attempted_keys = []

    def _save(self, *args, **kwargs):
        attempted_keys.append(self.key)
        if len(attempted_keys) <= failures:
            raise IntegrityError("duplicate key value violates unique constraint")
        return real_save(self, *args, **kwargs)

    return _save, attempted_keys


@pytest.fixture
def project_creator(api_client, user, grant, organization):
    grant(user, org=organization, role=OrganizationRole.ADMIN)
    return api_client(user)


@pytest.fixture
def environment_creator(api_client, user, grant, organization, project):
    grant(user, org=organization, role=OrganizationRole.USER)
    grant(user, project=project, role=ProjectRole.ADMIN)
    return api_client(user)


@pytest.mark.django_db
class TestProjectKeyDerivedFromName:
    def test_create_without_a_key_derives_one_from_the_name(self, project_creator, organization):
        response = project_creator.post(
            PROJECTS_URL,
            {"organization": str(organization.id), "name": "Mobile App"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "mobile-app"
        assert Project.objects.get(id=response.data["id"]).key == "mobile-app"

    def test_derived_key_that_collides_in_the_organization_gets_a_suffix(
        self, project_creator, organization
    ):
        Project.objects.create(organization=organization, name="Mobile App", key="mobile-app")

        response = project_creator.post(
            PROJECTS_URL,
            {"organization": str(organization.id), "name": "Mobile App"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "mobile-app-2"

    def test_derived_key_ignores_collisions_in_other_organizations(
        self, project_creator, organization, make_project
    ):
        other_organization = make_project(name="Other").organization
        Project.objects.create(organization=other_organization, name="Mobile App", key="mobile-app")

        response = project_creator.post(
            PROJECTS_URL,
            {"organization": str(organization.id), "name": "Mobile App"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "mobile-app"

    def test_a_name_that_slugifies_to_nothing_still_creates(self, project_creator, organization):
        response = project_creator.post(
            PROJECTS_URL,
            {"organization": str(organization.id), "name": "🚀🚀🚀"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] != ""

    def test_an_explicitly_sent_key_is_honoured_exactly(self, project_creator, organization):
        response = project_creator.post(
            PROJECTS_URL,
            {"organization": str(organization.id), "name": "Mobile App", "key": "legacy-mob"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "legacy-mob"


@pytest.mark.django_db
class TestProjectKeyIsNotRederivedOnUpdate:
    def test_renaming_a_project_leaves_its_key_alone(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"{PROJECTS_URL}{project.id}/", {"name": "Completely Different"}, format="json"
        )

        assert response.status_code == 200
        project.refresh_from_db()
        assert project.name == "Completely Different"
        assert project.key == "default"

    def test_the_key_is_still_editable_on_its_own(
        self, api_client, user, grant, organization, project
    ):
        grant(user, org=organization, role=OrganizationRole.ADMIN)
        client = api_client(user)

        response = client.patch(f"{PROJECTS_URL}{project.id}/", {"key": "chosen"}, format="json")

        assert response.status_code == 200
        project.refresh_from_db()
        assert project.key == "chosen"


@pytest.mark.django_db
class TestProjectKeyRace:
    def test_losing_the_race_retries_with_a_fresh_key(self, project_creator, organization):
        save, attempted_keys = flaky_save(Project, failures=1)

        with patch.object(Project, "save", save):
            response = project_creator.post(
                PROJECTS_URL,
                {"organization": str(organization.id), "name": "Mobile App"},
                format="json",
            )

        assert response.status_code == 201
        # The retry must not re-offer the key that just lost.
        assert attempted_keys == ["mobile-app", "mobile-app-2"]
        assert response.data["key"] == "mobile-app-2"

    def test_losing_every_attempt_is_a_400_not_a_500(self, project_creator, organization):
        save, attempted_keys = flaky_save(Project, failures=DERIVED_KEY_MAX_ATTEMPTS)

        with patch.object(Project, "save", save):
            response = project_creator.post(
                PROJECTS_URL,
                {"organization": str(organization.id), "name": "Mobile App"},
                format="json",
            )

        assert response.status_code == 400
        assert "key" in response.data
        assert len(attempted_keys) == DERIVED_KEY_MAX_ATTEMPTS
        assert not Project.objects.filter(organization=organization, name="Mobile App").exists()

    def test_an_explicit_key_that_loses_the_race_is_a_400_and_is_never_rewritten(
        self, project_creator, organization
    ):
        # An explicit key is a request, not a suggestion: silently storing a
        # different one would be worse than refusing.
        save, attempted_keys = flaky_save(Project, failures=1)

        with patch.object(Project, "save", save):
            response = project_creator.post(
                PROJECTS_URL,
                {"organization": str(organization.id), "name": "Mobile App", "key": "chosen"},
                format="json",
            )

        assert response.status_code == 400
        assert attempted_keys == ["chosen"]


@pytest.mark.django_db
class TestEnvironmentKeyDerivedFromName:
    def test_create_without_a_key_derives_one_from_the_name(self, environment_creator, project):
        response = environment_creator.post(
            ENVIRONMENTS_URL,
            {"project": str(project.id), "name": "Staging EU"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "staging-eu"
        assert Environment.objects.get(id=response.data["id"]).key == "staging-eu"

    def test_derived_key_that_collides_in_the_project_gets_a_suffix(
        self, environment_creator, project
    ):
        Environment.objects.create(project=project, name="Staging", key="staging")

        response = environment_creator.post(
            ENVIRONMENTS_URL,
            {"project": str(project.id), "name": "Staging"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "staging-2"

    def test_derived_key_ignores_collisions_in_other_projects(
        self, environment_creator, project, make_project, make_environment
    ):
        make_environment(project=make_project(name="Other"), key="staging", name="Staging")

        response = environment_creator.post(
            ENVIRONMENTS_URL,
            {"project": str(project.id), "name": "Staging"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "staging"

    def test_a_name_that_slugifies_to_nothing_still_creates(self, environment_creator, project):
        response = environment_creator.post(
            ENVIRONMENTS_URL,
            {"project": str(project.id), "name": "🚀🚀🚀"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] != ""

    def test_an_explicitly_sent_key_is_honoured_exactly(self, environment_creator, project):
        response = environment_creator.post(
            ENVIRONMENTS_URL,
            {"project": str(project.id), "name": "Staging EU", "key": "eu"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["key"] == "eu"


@pytest.mark.django_db
class TestEnvironmentKeyIsNotRederivedOnUpdate:
    def test_renaming_an_environment_leaves_its_key_alone(
        self, api_client, user, grant, organization, environment
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, environment=environment, role=EnvironmentRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"{ENVIRONMENTS_URL}{environment.id}/",
            {"name": "Completely Different"},
            format="json",
        )

        assert response.status_code == 200
        environment.refresh_from_db()
        assert environment.name == "Completely Different"
        assert environment.key == "prod"

    def test_the_key_is_still_editable_on_its_own(
        self, api_client, user, grant, organization, environment
    ):
        grant(user, org=organization, role=OrganizationRole.USER)
        grant(user, environment=environment, role=EnvironmentRole.ADMIN)
        client = api_client(user)

        response = client.patch(
            f"{ENVIRONMENTS_URL}{environment.id}/", {"key": "chosen"}, format="json"
        )

        assert response.status_code == 200
        environment.refresh_from_db()
        assert environment.key == "chosen"


@pytest.mark.django_db
class TestEnvironmentKeyRace:
    def test_losing_the_race_retries_with_a_fresh_key(self, environment_creator, project):
        save, attempted_keys = flaky_save(Environment, failures=1)

        with patch.object(Environment, "save", save):
            response = environment_creator.post(
                ENVIRONMENTS_URL,
                {"project": str(project.id), "name": "Staging"},
                format="json",
            )

        assert response.status_code == 201
        assert attempted_keys == ["staging", "staging-2"]
        assert response.data["key"] == "staging-2"

    def test_losing_every_attempt_is_a_400_not_a_500(self, environment_creator, project):
        save, attempted_keys = flaky_save(Environment, failures=DERIVED_KEY_MAX_ATTEMPTS)

        with patch.object(Environment, "save", save):
            response = environment_creator.post(
                ENVIRONMENTS_URL,
                {"project": str(project.id), "name": "Staging"},
                format="json",
            )

        assert response.status_code == 400
        assert "key" in response.data
        assert len(attempted_keys) == DERIVED_KEY_MAX_ATTEMPTS
        assert not Environment.objects.filter(project=project, name="Staging").exists()
