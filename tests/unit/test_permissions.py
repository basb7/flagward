"""
Tests for the standalone permission classes and viewset mixin (design D5).

Nothing here is wired to a real viewset yet — that is slice 4's job. These
tests exercise the classes directly, against fakes that carry only the
attributes `HasCapability`/`TenantScopedViewSetMixin` actually read, so that
slice 4 becomes a wiring review rather than a semantics review.
"""
import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIRequestFactory

from tenancy.capabilities import Capability
from tenancy.models import EnvironmentRole, OrganizationRole
from tenancy.permissions import HasCapability, IsDashboardUser, TenantScopedViewSetMixin

factory = APIRequestFactory()


class _FakeView:
    """The minimal surface `HasCapability` reads off a viewset."""

    def __init__(self, action, capability_map, environment_of=None):
        self.action = action
        self._capability_map = capability_map
        self._environment_of = environment_of or (lambda obj: obj)

    def capability_for_action(self, action):
        return self._capability_map[action]

    def environment_of(self, obj):
        return self._environment_of(obj)


@pytest.mark.django_db
class TestIsDashboardUser:
    def test_authenticated_user_is_allowed(self, user):
        request = factory.get("/api/v1/flags/")
        request.user = user

        assert IsDashboardUser().has_permission(request, view=None) is True

    def test_environment_principal_is_denied(self, environment):
        """SDKAuthentication's principal is an Environment, not a User (spec: Non-User Principal Fails Closed)."""
        request = factory.get("/api/v1/flags/")
        request.user = environment

        assert IsDashboardUser().has_permission(request, view=None) is False

    def test_environment_principal_raises_no_attribute_error(self, environment):
        """The whole point: no AttributeError, just a clean False (-> 403)."""
        request = factory.get("/api/v1/flags/")
        request.user = environment

        # Must not raise, even though Environment has no is_authenticated.
        IsDashboardUser().has_permission(request, view=None)


@pytest.mark.django_db
class TestHasCapability:
    def test_safe_method_is_always_allowed(self, user):
        request = factory.get("/api/v1/flags/")
        request.user = user
        view = _FakeView(action="list", capability_map={})

        assert HasCapability().has_permission(request, view) is True

    def test_unsafe_method_denied_without_the_capability_anywhere(self, user):
        request = factory.post("/api/v1/flags/")
        request.user = user
        view = _FakeView(action="create", capability_map={"create": Capability.FLAG_EDIT})

        assert HasCapability().has_permission(request, view) is False

    def test_unsafe_method_allowed_when_capability_held_somewhere(self, environment, user, grant):
        # `has_permission` is backed by `environments_with`, which requires
        # (Layer 2) that the user still belong to the environment's
        # organization -- unlike `capabilities_for` below, which the
        # object-permission tests deliberately exercise in isolation.
        grant(user, org=environment.project.organization, role=OrganizationRole.USER)
        grant(user, environment=environment, role=EnvironmentRole.EDITOR)
        request = factory.post("/api/v1/flags/")
        request.user = user
        view = _FakeView(action="create", capability_map={"create": Capability.FLAG_EDIT})

        assert HasCapability().has_permission(request, view) is True

    def test_has_object_permission_matches_capabilities_for(self, environment, flag, user, grant):
        grant(user, environment=environment, role=EnvironmentRole.VIEWER)
        request = factory.patch(f"/api/v1/flags/{flag.pk}/")
        request.user = user
        view = _FakeView(
            action="partial_update",
            capability_map={"partial_update": Capability.FLAG_EDIT},
            environment_of=lambda obj: obj.environment,
        )

        # VIEWER holds no flag.edit.
        assert HasCapability().has_object_permission(request, view, flag) is False

    def test_has_object_permission_true_with_the_capability(self, environment, flag, user, grant):
        grant(user, environment=environment, role=EnvironmentRole.EDITOR)
        request = factory.patch(f"/api/v1/flags/{flag.pk}/")
        request.user = user
        view = _FakeView(
            action="partial_update",
            capability_map={"partial_update": Capability.FLAG_EDIT},
            environment_of=lambda obj: obj.environment,
        )

        assert HasCapability().has_object_permission(request, view, flag) is True


@pytest.mark.django_db
class TestTenantScopedViewSetMixin:
    def test_get_queryset_raises_when_environment_lookup_unset(self, user):
        class _Unconfigured(TenantScopedViewSetMixin):
            def get_queryset(self):  # noqa: D401 - mirrors the mixin's own signature
                return super().get_queryset()

        instance = _Unconfigured()
        with pytest.raises(ImproperlyConfigured):
            instance.get_queryset()

    def test_capability_for_action_raises_when_action_unmapped(self):
        class _Configured(TenantScopedViewSetMixin):
            environment_lookup = ""
            capability_map = {"list": Capability.ENVIRONMENT_VIEW}

        instance = _Configured()
        with pytest.raises(ImproperlyConfigured):
            instance.capability_for_action("destroy")

    def test_capability_for_action_returns_the_mapped_capability(self):
        class _Configured(TenantScopedViewSetMixin):
            environment_lookup = ""
            capability_map = {"partial_update": Capability.FLAG_EDIT}

        instance = _Configured()
        assert instance.capability_for_action("partial_update") == Capability.FLAG_EDIT

    def test_environment_of_traverses_the_declared_lookup(self, environment, flag):
        class _Configured(TenantScopedViewSetMixin):
            environment_lookup = "environment"
            capability_map = {}

        instance = _Configured()
        assert instance.environment_of(flag) == environment

    def test_environment_of_identity_when_lookup_is_empty(self, environment):
        class _Configured(TenantScopedViewSetMixin):
            environment_lookup = ""
            capability_map = {}

        instance = _Configured()
        assert instance.environment_of(environment) == environment
