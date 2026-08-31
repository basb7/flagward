"""
Shared fixture layer for the whole test suite.

All fixtures are function-scoped. Session or module scope would need
`django_db_setup`/`django_db_blocker` gymnastics to survive pytest-django's
per-test transaction rollback, and would leak rows between tests — not worth
it for the handful of extra inserts per run these fixtures cost.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core_flags.models import Environment, FeatureFlag
from tenancy.models import (
    EnvironmentMembership,
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
)

MEMBERSHIP_TABLES = frozenset(
    {
        OrganizationMembership._meta.db_table,
        ProjectMembership._meta.db_table,
        EnvironmentMembership._meta.db_table,
    }
)


@pytest.fixture
def organization():
    return Organization.objects.create(name="Acme", plan="COMMUNITY")


@pytest.fixture
def make_project():
    """Callable for tests needing more than one project/organization."""

    def _make_project(*, organization=None, name="Acme", key=None):
        org = organization or Organization.objects.create(name=name, plan="COMMUNITY")
        return Project.objects.create(
            organization=org, name=name, key=key or org.name.lower().replace(" ", "-")
        )

    return _make_project


@pytest.fixture
def project(organization):
    return Project.objects.create(organization=organization, name="Default", key="default")


@pytest.fixture
def make_environment():
    """Callable for tests needing more than one environment."""

    def _make_environment(*, project, key="prod", name="Production"):
        return Environment.objects.create(project=project, key=key, name=name)

    return _make_environment


@pytest.fixture
def environment(project):
    """The drop-in replacement for the 44 sites that used to omit `project`."""
    return Environment.objects.create(project=project, key="prod", name="Production")


@pytest.fixture
def make_flag():
    """Callable for tests needing more than one flag."""

    def _make_flag(*, environment, key="flag", name="Flag", **extra):
        return FeatureFlag.objects.create(environment=environment, key=key, name=name, **extra)

    return _make_flag


@pytest.fixture
def flag(environment):
    return FeatureFlag.objects.create(environment=environment, key="flag", name="Flag")


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="dash", email="dash@example.com", password="secret"
    )


@pytest.fixture
def grant():
    """Callable building a membership row at exactly one level per call."""

    def _grant(user, *, org=None, project=None, environment=None, role):
        if sum(target is not None for target in (org, project, environment)) != 1:
            raise ValueError("grant() takes exactly one of org, project, environment")
        if org is not None:
            return OrganizationMembership.objects.create(organization=org, user=user, role=role)
        if project is not None:
            return ProjectMembership.objects.create(project=project, user=user, role=role)
        return EnvironmentMembership.objects.create(environment=environment, user=user, role=role)

    return _grant


@pytest.fixture
def api_client():
    """Callable returning an authenticated APIClient for a given user."""

    def _api_client(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _api_client


@pytest.fixture
def assert_membership_never_joined():
    """
    The scoping invariant, asserted rather than grepped (design D4).

    `alias_map` holds only the OUTER query's tables; subqueries live in the
    where-tree and never appear here. A membership table showing up there
    means somebody wrote a join instead of a scalar subquery.
    """

    def _assert(queryset):
        assert MEMBERSHIP_TABLES.isdisjoint(queryset.query.alias_map), queryset.query.alias_map
        assert queryset.query.distinct is False

    return _assert


@pytest.fixture(autouse=True)
def _fast_password_hashing(settings):
    """
    Swap the production hasher for a cheap one across the suite.

    Django's default PBKDF2 hasher is deliberately slow, which is right in
    production and pure cost in tests: nothing here asserts anything about how
    a password is stored, only that authentication succeeds or does not.
    """
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
