"""
Reusable DRF mixins shared across app APIs.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

TRUE_LITERALS = {"true", "1", "yes", "on"}
FALSE_LITERALS = {"false", "0", "no", "off"}


class QueryParamFilterMixin:
    """
    Filter a queryset by exact-match query params.

    Declare the allowed params in `filter_fields`, either as a tuple of names
    that double as ORM lookups, or as a dict mapping the public param name to
    its ORM lookup:

        filter_fields = ("flag", "result")
        filter_fields = {"environment": "flag__environment"}

    Name boolean params in `boolean_filter_fields` so `?result=false` works;
    Django's BooleanField only accepts capitalised literals on its own.

    Params absent from the request are ignored. A value the database cannot
    coerce (e.g. a malformed UUID) raises a 400 rather than silently returning
    an empty page, which would read as "no data" instead of "bad request".
    """

    filter_fields: tuple[str, ...] | dict[str, str] = ()
    boolean_filter_fields: tuple[str, ...] = ()

    def _param_lookups(self) -> dict[str, str]:
        if isinstance(self.filter_fields, dict):
            return self.filter_fields
        return {field: field for field in self.filter_fields}

    def _coerce(self, param: str, value: str):
        if param not in self.boolean_filter_fields:
            return value

        normalized = value.strip().lower()
        if normalized in TRUE_LITERALS:
            return True
        if normalized in FALSE_LITERALS:
            return False
        raise ValidationError(
            {param: f"Expected a boolean value, got '{value}'."}
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        filters = {
            lookup: self._coerce(param, self.request.query_params[param])
            for param, lookup in self._param_lookups().items()
            if self.request.query_params.get(param)
        }

        if not filters:
            return queryset

        try:
            return queryset.filter(**filters)
        except (DjangoValidationError, ValueError, TypeError) as exc:
            raise ValidationError({"detail": f"Invalid filter value: {exc}"}) from exc
