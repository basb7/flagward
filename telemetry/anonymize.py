"""
Mappings that turn client-controlled or fingerprintable values into coarse,
safe ones before they leave the installation.
"""
from sdk_api.models import SDKType
from telemetry.version import UNKNOWN, is_semver
from tenancy.models import Plan

OTHER = "other"

_KNOWN_SDK_TYPES = frozenset(value.lower() for value in SDKType.values)

# Half-open ranges: a count belongs to the first bucket whose upper bound it is
# below. Zero gets its own bucket so "installed but unused" stays visible.
_EVALUATION_BUCKETS = (
    (1, "0"),
    (100, "1-100"),
    (1_000, "100-1k"),
    (10_000, "1k-10k"),
    (100_000, "10k-100k"),
)
_EVALUATION_BUCKET_MAX = "100k+"


def sdk_type_name(raw: str | None) -> str:
    """`sdk_register` never validates `sdk_type`, so anything off the allowlist is "other"."""
    name = (raw or "").strip().lower()
    return name if name in _KNOWN_SDK_TYPES else OTHER


def sdk_version(raw: str | None) -> str:
    value = (raw or "").strip()
    return value if is_semver(value) else UNKNOWN


def plan_name(raw: str | None) -> str:
    return raw if raw in Plan.values else OTHER


def evaluation_bucket(count: int) -> str:
    for upper, label in _EVALUATION_BUCKETS:
        if count < upper:
            return label
    return _EVALUATION_BUCKET_MAX
