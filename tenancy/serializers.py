"""
Serializer-level FK narrowing (design D5, Layer 2 -- the only create-time gate).

DRF has no object on `POST`, so `HasCapability.has_object_permission` never
runs and Layer 3 cannot express "which environment" for a create. Narrowing a
related field's own queryset is what actually stops a cross-tenant write.
"""
from __future__ import annotations

import logging
from typing import Callable

from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


class CapabilityScopedFKMixin:
    """
    Narrows the querysets of one or more `PrimaryKeyRelatedField`s to the
    objects the requesting user holds the mapped capability on.

    Subclasses declare `capability_scoped_fields` as
    `{field_name: (capability, build)}`, where `build(user, capability)`
    returns the narrowed queryset for that field.
    """

    capability_scoped_fields: dict[str, tuple[str, Callable]] = {}

    def get_fields(self):
        fields = super().get_fields()
        user = self._scoping_user()
        for name, (capability, build) in self.capability_scoped_fields.items():
            if name not in fields:
                continue
            if user is not None:
                fields[name].queryset = build(user, capability)
            else:
                # Fail-closed, not unnarrowed and not an exception: a
                # serializer instantiated outside a request (management
                # command, nested write, a test) must not silently fall back
                # to the field's full `objects.all()` -- that is the exact
                # hole this mixin exists to close. Reads are unaffected
                # because `PrimaryKeyRelatedField.to_representation` reads
                # `value.pk` and never consults the queryset.
                logger.warning(
                    "%s.%s narrowed to .none(): no request/User in serializer context",
                    type(self).__name__,
                    name,
                )
                fields[name].queryset = fields[name].queryset.none()
        return fields

    def _scoping_user(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return user if isinstance(user, User) else None
