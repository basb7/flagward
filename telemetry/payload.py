"""
Builds the schema v1 telemetry payload.

Only counts, booleans, enums and versions leave the installation. Every field
here is listed in docs/telemetry.md, and tests/integration/test_telemetry_payload.py
fails when one is added without updating that contract.
"""
import os
import platform
from datetime import datetime, timedelta

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, Q
from django.utils import timezone

from core_flags.models import Environment, FeatureFlag, FlagOverride, FlagType, StrategyRule, Variant
from sdk_api.models import EvaluationLog, SDKRegistration
from telemetry.anonymize import evaluation_bucket, plan_name, sdk_type_name, sdk_version
from telemetry.models import InstallationIdentity
from telemetry.version import get_version
from tenancy.models import Organization, Project

SCHEMA_VERSION = 1

DOCKERENV = "/.dockerenv"

SDK_ACTIVE_WINDOW = timedelta(days=7)
EVALUATION_WINDOW = timedelta(hours=24)

REDIS_CACHE_BACKEND = "django.core.cache.backends.redis.RedisCache"


def build_payload(identity: InstallationIdentity, *, now: datetime | None = None, server: str = "unknown") -> dict:
    now = now or timezone.now()
    return {
        "schema_version": SCHEMA_VERSION,
        "installation_id": str(identity.installation_id),
        "sent_at": now.isoformat(),
        "first_seen_at": identity.first_seen_at.isoformat(),
        "flagward_version": get_version(),
        "mode": "development" if settings.DEBUG else "production",
        "server": server,
        "runtime": _runtime(),
        "usage": _usage(),
        "sdks": _sdks(now),
        "evaluations_24h_bucket": evaluation_bucket(
            EvaluationLog.objects.filter(timestamp__gte=now - EVALUATION_WINDOW).count()
        ),
    }


def _runtime() -> dict:
    python = platform.python_version_tuple()
    return {
        "python": f"{python[0]}.{python[1]}",
        "django": f"{django.VERSION[0]}.{django.VERSION[1]}",
        "deployment": "docker" if os.path.exists(DOCKERENV) else "bare",
        "database": connection.vendor,
        "redis_enabled": settings.CACHES.get("default", {}).get("BACKEND") == REDIS_CACHE_BACKEND,
        "email_configured": bool(settings.EMAIL_HOST),
        "default_plan": plan_name(settings.DEFAULT_ORGANIZATION_PLAN),
    }


def _usage() -> dict:
    flags = FeatureFlag.objects.aggregate(
        total=Count("id"),
        boolean=Count("id", filter=Q(flag_type=FlagType.BOOLEAN)),
        multivariate=Count("id", filter=Q(flag_type=FlagType.MULTIVARIATE)),
    )
    return {
        "organizations": Organization.objects.count(),
        "projects": Project.objects.count(),
        "environments": Environment.objects.count(),
        "users": get_user_model().objects.filter(is_active=True).count(),
        "flags": flags,
        "flags_with_rules": FeatureFlag.objects.filter(rules__isnull=False).distinct().count(),
        "strategy_rules": StrategyRule.objects.count(),
        "rules_with_rollout": StrategyRule.objects.filter(rollout_variant__isnull=False).count(),
        "variants": Variant.objects.count(),
        "active_overrides": FlagOverride.objects.active().count(),
    }


def _sdks(now: datetime) -> list[dict]:
    """
    One entry per (type, version), counting the environments that saw that SDK
    in the last 7 days -- a registration is one row per environment and SDK
    type, not one per running app.
    """
    counts: dict[tuple[str, str], int] = {}
    recent = SDKRegistration.objects.filter(last_seen_at__gte=now - SDK_ACTIVE_WINDOW)
    for raw_type, raw_version in recent.values_list("sdk_type", "version"):
        key = (sdk_type_name(raw_type), sdk_version(raw_version))
        counts[key] = counts.get(key, 0) + 1
    return [
        {"type": sdk_type, "version": version, "active_7d": count}
        for (sdk_type, version), count in sorted(counts.items())
    ]
