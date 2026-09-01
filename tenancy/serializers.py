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
from django.db import IntegrityError, transaction
from rest_framework import serializers

from tenancy.slugs import DERIVED_KEY_MAX_ATTEMPTS, unique_key

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


class DerivedKeyMixin:
    """
    Derives a slug `key` from `name` when the client omits it on create.

    Nothing resolves `Project.key` or `Environment.key` -- no URL, filter,
    lookup or SDK path -- so making a human invent one before they could
    create anything was a toll on a road to nowhere. The server derives it
    instead, through the single definition in `tenancy.slugs.unique_key`.

    Three rules the subclasses inherit rather than each re-deciding:

    * A `key` the client actually sends is honoured verbatim. This is not a
      generated-only field; the rename dialogs write it directly.
    * On update the key is NEVER re-derived. Renaming must not silently move
      a key out from under whoever is reading it -- a key that changes by
      itself is worse than one you typed on purpose.
    * A derived key that loses a uniqueness race to a concurrent create comes
      back with the next free key instead of surfacing the raw
      `IntegrityError` as a 500.

    Subclasses set `derived_key_queryset()` to the uniqueness scope the
    model's constraint actually uses -- the organization for `Project`, the
    project for `Environment`.
    """

    #: The slug field to fill in, and the human-facing field to derive it from.
    derived_key_field = "key"
    derived_key_source = "name"

    #: Whether *this* request's key was generated rather than sent. Only a
    #: generated key may be regenerated after a race; a client's own key is a
    #: request, not a suggestion, so it is refused rather than rewritten.
    _key_is_derived = False

    def derived_key_queryset(self, attrs):
        """Rows the new key must be unique among. Subclass responsibility."""
        raise NotImplementedError

    def to_internal_value(self, data):
        # Derived here, not in `create()`, so the model's own uniqueness
        # validator sees the key like any other: DRF's `UniqueTogetherValidator`
        # runs on the output of this method and would otherwise report the
        # field as missing.
        attrs = super().to_internal_value(data)
        if self.instance is None and not attrs.get(self.derived_key_field):
            attrs[self.derived_key_field] = self._derive_key(attrs)
            self._key_is_derived = True
        return attrs

    def _derive_key(self, attrs, taken=()):
        model_field = self.Meta.model._meta.get_field(self.derived_key_field)
        return unique_key(
            base_name=attrs.get(self.derived_key_source) or "",
            queryset=self.derived_key_queryset(attrs),
            field=self.derived_key_field,
            max_length=model_field.max_length,
            taken=taken,
        )

    def create(self, validated_data):
        """
        Create the row, re-deriving the key if the database rejects it.

        Two concurrent creates from the same name both read the same slug as
        free; the loser's `INSERT` violates the uniqueness constraint. Each
        attempt runs in its own savepoint because a failed statement poisons
        the surrounding transaction, and the key that just lost is fed back
        as `taken` -- the winning row may not be visible to this snapshot
        yet, and re-offering the same key would only lose again.

        The retry is bounded. Whether the collision is a genuine race or a
        constraint that will reject every candidate, the caller gets a 400
        naming the field rather than a 500 naming nothing.
        """
        attempts = DERIVED_KEY_MAX_ATTEMPTS if self._key_is_derived else 1
        already_lost = set()

        for attempt in range(1, attempts + 1):
            try:
                with transaction.atomic():
                    return super().create(validated_data)
            except IntegrityError as exc:
                # `exc` is logged, not inspected: telling a key collision from
                # any other violated constraint means matching backend-specific
                # constraint names, which drift between Postgres and sqlite.
                # So the 400 below always names the key -- and this line is
                # what proves it right or wrong the day it isn't.
                logger.warning(
                    "%s create lost key %r (attempt %d/%d): %s",
                    type(self).__name__,
                    validated_data.get(self.derived_key_field),
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    raise serializers.ValidationError(
                        {self.derived_key_field: self._key_collision_message()}
                    ) from None
                already_lost.add(validated_data[self.derived_key_field])
                validated_data[self.derived_key_field] = self._derive_key(
                    validated_data, taken=already_lost
                )

    def _key_collision_message(self):
        if self._key_is_derived:
            return "Could not derive a free key for this name. Please try again."
        return "This key is already taken."
