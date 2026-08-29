"""
Standalone DRF permission classes and viewset mixin (design D5).

Nothing here is attached to any viewset, serializer, or settings value in
this slice — that wiring is slice 4's job. Every class is unit-tested here in
isolation so slice 4 can stay a wiring review instead of a semantics review.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import SAFE_METHODS, BasePermission

from tenancy.capabilities import Capability
from tenancy.scoping import capabilities_for, environments_with

User = get_user_model()

_UNSET = object()


class IsDashboardUser(BasePermission):
    """
    A dashboard route requires a Django `User` principal, never an api-key
    principal (spec/access-control: Non-User Principal Fails Closed).

    `SDKAuthentication` returns an `Environment` as `request.user`, which has
    no `is_authenticated` attribute. Checking `isinstance` first means that
    principal gets a clean 403 instead of an unhandled `AttributeError`/500.
    """

    def has_permission(self, request, view) -> bool:
        return isinstance(request.user, User) and request.user.is_authenticated


class HasCapability(BasePermission):
    """
    Capability-gated permission (spec/access-control: Capability-Gated
    Actions Return 403). Carries no policy of its own: every decision is
    delegated to `tenancy.scoping`, which is itself proven equal to
    `resolve_capabilities` by test.
    """

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True  # Layer 1 (queryset scoping) already scoped the read.
        capability = view.capability_for_action(view.action)
        return environments_with(request.user, capability).exists()

    def has_object_permission(self, request, view, obj) -> bool:
        capability = view.capability_for_action(view.action)
        return capability in capabilities_for(request.user, view.environment_of(obj))


class TenantScopedViewSetMixin:
    """
    Wires a `ModelViewSet` to join-free tenant scoping (design D4/D5, Layer 1
    — queryset scoping).

    Subclasses (slice 4) set two class attributes:

    - `environment_lookup`: the ORM path, in Django's `__`-separated form,
      from this viewset's model down to its owning `Environment` (`""` for
      `EnvironmentViewSet` itself, `"environment"` for `FeatureFlagViewSet`,
      `"flag__environment"` for `StrategyRuleViewSet`, ...).
    - `capability_map`: DRF action name -> the capability required for that
      action, consumed by `HasCapability` through `capability_for_action`.

    Leaving `environment_lookup` at its `_UNSET` sentinel raises
    `ImproperlyConfigured` at first request, rather than silently falling
    back to an unscoped `Model.objects.all()`.
    """

    environment_lookup: str = _UNSET
    capability_map: dict[str, str] = {}

    def get_queryset(self):
        if self.environment_lookup is _UNSET:
            raise ImproperlyConfigured(
                f"{type(self).__name__} must set environment_lookup to use TenantScopedViewSetMixin"
            )
        queryset = super().get_queryset()
        visible = environments_with(self.request.user, Capability.ENVIRONMENT_VIEW)
        lookup = f"{self.environment_lookup}__in" if self.environment_lookup else "pk__in"
        return queryset.filter(**{lookup: visible})

    def capability_for_action(self, action: str) -> str:
        try:
            return self.capability_map[action]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"{type(self).__name__} has no capability mapped for action {action!r}"
            ) from exc

    def environment_of(self, obj):
        if not self.environment_lookup or self.environment_lookup is _UNSET:
            return obj
        target = obj
        for part in self.environment_lookup.split("__"):
            target = getattr(target, part)
        return target
