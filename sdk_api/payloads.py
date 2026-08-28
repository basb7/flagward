"""
SDK wire format.

SDKs evaluate locally, so the payload has to carry the *effective* state of a
flag, not its raw configuration. This module is the single place that projection
happens — the flags endpoint and the SSE stream both use it so they cannot drift.
"""
from core_flags.models import FeatureFlag, FlagOverride


def active_overrides_by_flag(environment) -> dict:
    """
    Map of flag id -> active override for one environment, in a single query.

    Fetched in bulk on purpose: resolving the override per flag turns the SDK's
    hot path into an N+1.
    """
    overrides = (
        FlagOverride.objects.active()
        .filter(flag__environment=environment)
        .order_by("flag_id", "-created_at")
    )

    by_flag = {}
    for override in overrides:
        # Ordered newest-first within each flag, so the first one wins.
        by_flag.setdefault(override.flag_id, override)
    return by_flag


def serialize_flag(flag: FeatureFlag, override: FlagOverride | None = None) -> dict:
    """
    Project one flag onto the SDK wire format.

    An active override forces the value and strips the rules, which mirrors
    `FlagEvaluationService`: with no rules left, the SDK's local evaluation of
    `is_enabled` is the override's value and nothing else can contradict it.
    """
    if override is not None:
        return {
            "key": flag.key,
            "name": flag.name,
            "is_enabled": override.is_enabled,
            "flag_type": flag.flag_type,
            "rules": [],
            "overridden": True,
        }

    rules_data = []
    for rule in flag.rules.all():
        rules_data.append(
            {
                "priority": rule.priority,
                "operator_logic": rule.operator_logic,
                "conditions": [
                    {
                        "attribute": condition.attribute,
                        "operator": condition.operator,
                        "value": condition.value,
                    }
                    for condition in rule.conditions.all()
                ],
            }
        )

    return {
        "key": flag.key,
        "name": flag.name,
        "is_enabled": flag.is_enabled,
        "flag_type": flag.flag_type,
        "rules": rules_data,
        "overridden": False,
    }


def serialize_environment_flags(environment) -> list[dict]:
    """Every flag in an environment, projected onto the SDK wire format."""
    overrides = active_overrides_by_flag(environment)
    flags = FeatureFlag.objects.filter(environment=environment).prefetch_related(
        "rules", "rules__conditions"
    )
    return [serialize_flag(flag, overrides.get(flag.id)) for flag in flags]
