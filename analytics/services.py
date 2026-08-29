"""
Aggregation services for the analytics API.

All aggregation lives here so it can be exercised without going through HTTP.
Views stay thin: parse params, call a service, return the dict.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any

from django.db.models import BooleanField, Count, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import TruncHour
from django.utils import timezone

from core_flags.models import Environment, FeatureFlag, FlagOverride
from sdk_api.models import EvaluationLog, SDKRegistration

# An SDK that has not polled within this window is considered stale, not active.
SDK_ACTIVE_WINDOW = timedelta(minutes=5)

MAX_TIMESERIES_HOURS = 168  # 7 days
MAX_TOP_FLAGS = 50


def parse_uuid(raw: str | None) -> uuid.UUID | None:
    """Return a UUID, or None when `raw` is absent or malformed."""
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


def clamp(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Coerce `value` to an int inside [minimum, maximum], falling back to `default`."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _scope(queryset: QuerySet, environments: QuerySet[Environment], lookup: str) -> QuerySet:
    """
    Narrow a queryset to `environments`.

    `.values("pk")` is explicit rather than relying on Django's implicit pk
    coercion for `__in`, because the caller's queryset may carry
    `select_related`.
    """
    return queryset.filter(**{f"{lookup}__in": environments.values("pk")})


def _true_rate(total: int, true_count: int) -> float | None:
    """Share of evaluations that resolved to True, or None when there is no data."""
    if not total:
        return None
    return round(true_count / total, 4)


def build_overview(environments: QuerySet[Environment]) -> dict[str, Any]:
    """Counters for the dashboard home: flags, SDKs, evaluations and overrides."""
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    sdk_active_since = now - SDK_ACTIVE_WINDOW

    flags = _scope(FeatureFlag.objects.all(), environments, "environment")

    # `enabled` is the configured state; `effective_enabled` is what SDKs serve
    # once active overrides are applied. Reporting only the former would show a
    # force-disabled flag as enabled.
    newest_active_override = (
        FlagOverride.objects.active()
        .filter(flag=OuterRef("pk"))
        .order_by("-created_at")
        .values("is_enabled")[:1]
    )
    flag_counts = flags.annotate(
        override_value=Subquery(newest_active_override, output_field=BooleanField()),
    ).aggregate(
        total=Count("id"),
        enabled=Count("id", filter=Q(is_enabled=True)),
        overridden=Count("id", filter=Q(override_value__isnull=False)),
        effective_enabled=Count(
            "id",
            filter=Q(override_value=True)
            | Q(override_value__isnull=True, is_enabled=True),
        ),
    )

    registrations = _scope(SDKRegistration.objects.all(), environments, "environment")
    sdk_counts = registrations.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(last_seen_at__gte=sdk_active_since)),
    )

    evaluations = _scope(EvaluationLog.objects.all(), environments, "flag__environment")
    evaluation_counts = evaluations.aggregate(
        total=Count("id"),
        true_count=Count("id", filter=Q(result=True)),
        last_24h=Count("id", filter=Q(timestamp__gte=since_24h)),
        true_count_24h=Count("id", filter=Q(timestamp__gte=since_24h, result=True)),
    )

    overrides = _scope(FlagOverride.objects.all(), environments, "flag__environment")
    override_counts = overrides.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(cleared_at__isnull=True)),
        last_24h=Count("id", filter=Q(created_at__gte=since_24h)),
    )

    environments_total = environments.count()

    return {
        "generated_at": now.isoformat(),
        "environments": {"total": environments_total},
        "flags": {
            "total": flag_counts["total"],
            "enabled": flag_counts["enabled"],
            "disabled": flag_counts["total"] - flag_counts["enabled"],
            "effective_enabled": flag_counts["effective_enabled"],
            "overridden": flag_counts["overridden"],
        },
        "sdks": {
            "total": sdk_counts["total"],
            "active": sdk_counts["active"],
            "stale": sdk_counts["total"] - sdk_counts["active"],
            "active_window_minutes": int(SDK_ACTIVE_WINDOW.total_seconds() // 60),
        },
        "evaluations": {
            "total": evaluation_counts["total"],
            "last_24h": evaluation_counts["last_24h"],
            "true_rate": _true_rate(
                evaluation_counts["total"], evaluation_counts["true_count"]
            ),
            "true_rate_24h": _true_rate(
                evaluation_counts["last_24h"], evaluation_counts["true_count_24h"]
            ),
        },
        "overrides": {
            "total": override_counts["total"],
            "active": override_counts["active"],
            "last_24h": override_counts["last_24h"],
        },
    }


def build_evaluations_timeseries(
    environments: QuerySet[Environment], hours: int = 24
) -> dict[str, Any]:
    """
    Hourly evaluation counts over the last `hours` hours.

    Empty hours are emitted as zero buckets — a chart that silently skips them
    would misrepresent a gap in traffic as a shorter time range.
    """
    hours = clamp(hours, default=24, minimum=1, maximum=MAX_TIMESERIES_HOURS)
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    first_hour = current_hour - timedelta(hours=hours - 1)

    evaluations = _scope(
        EvaluationLog.objects.filter(timestamp__gte=first_hour),
        environments,
        "flag__environment",
    )

    rows = (
        evaluations.annotate(bucket=TruncHour("timestamp"))
        .values("bucket")
        .annotate(
            total=Count("id"),
            true_count=Count("id", filter=Q(result=True)),
        )
    )
    by_bucket: dict[datetime, dict[str, int]] = {row["bucket"]: row for row in rows}

    buckets = []
    for offset in range(hours):
        bucket_start = first_hour + timedelta(hours=offset)
        row = by_bucket.get(bucket_start)
        total = row["total"] if row else 0
        true_count = row["true_count"] if row else 0
        buckets.append(
            {
                "timestamp": bucket_start.isoformat(),
                "total": total,
                "true_count": true_count,
                "false_count": total - true_count,
            }
        )

    return {
        "hours": hours,
        "from": first_hour.isoformat(),
        "to": current_hour.isoformat(),
        "total": sum(bucket["total"] for bucket in buckets),
        "buckets": buckets,
    }


def build_top_flags(
    environments: QuerySet[Environment], hours: int = 24, limit: int = 5
) -> dict[str, Any]:
    """Most evaluated flags in the window, with their true rate."""
    hours = clamp(hours, default=24, minimum=1, maximum=MAX_TIMESERIES_HOURS)
    limit = clamp(limit, default=5, minimum=1, maximum=MAX_TOP_FLAGS)
    since = timezone.now() - timedelta(hours=hours)

    evaluations = _scope(
        EvaluationLog.objects.filter(timestamp__gte=since),
        environments,
        "flag__environment",
    )

    rows = (
        evaluations.values(
            "flag_id", "flag__key", "flag__name", "flag__environment__key"
        )
        .annotate(
            evaluations=Count("id"),
            true_count=Count("id", filter=Q(result=True)),
        )
        .order_by("-evaluations")[:limit]
    )

    return {
        "hours": hours,
        "limit": limit,
        "results": [
            {
                "flag": str(row["flag_id"]),
                "flag_key": row["flag__key"],
                "flag_name": row["flag__name"],
                "environment_key": row["flag__environment__key"],
                "evaluations": row["evaluations"],
                "true_count": row["true_count"],
                "false_count": row["evaluations"] - row["true_count"],
                "true_rate": _true_rate(row["evaluations"], row["true_count"]),
            }
            for row in rows
        ],
    }


def build_sdk_health(environments: QuerySet[Environment]) -> dict[str, Any]:
    """SDK fleet health, broken down by SDK type and version."""
    sdk_active_since = timezone.now() - SDK_ACTIVE_WINDOW
    registrations = _scope(SDKRegistration.objects.all(), environments, "environment")

    by_type = (
        registrations.values("sdk_type")
        .annotate(
            total=Count("id"),
            active=Count("id", filter=Q(last_seen_at__gte=sdk_active_since)),
        )
        .order_by("-total")
    )

    by_version = (
        registrations.values("sdk_type", "version")
        .annotate(total=Count("id"))
        .order_by("sdk_type", "-total")
    )

    totals = registrations.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(last_seen_at__gte=sdk_active_since)),
    )

    return {
        "active_window_minutes": int(SDK_ACTIVE_WINDOW.total_seconds() // 60),
        "total": totals["total"],
        "active": totals["active"],
        "stale": totals["total"] - totals["active"],
        "by_type": [
            {
                "sdk_type": row["sdk_type"],
                "total": row["total"],
                "active": row["active"],
                "stale": row["total"] - row["active"],
            }
            for row in by_type
        ],
        "by_version": [
            {
                "sdk_type": row["sdk_type"],
                "version": row["version"],
                "total": row["total"],
            }
            for row in by_version
        ],
    }
