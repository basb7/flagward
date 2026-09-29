"""
The Flagward version reported by telemetry.
"""
import re

from django.conf import settings

from config import version as version_module

UNKNOWN = "unknown"

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def is_semver(value: str | None) -> bool:
    return bool(value) and SEMVER.match(value) is not None


def get_version() -> str:
    """
    FLAGWARD_VERSION overrides the code version when set. Anything that is not
    semver is reported as "unknown" rather than sent as free text.
    """
    override = (settings.FLAGWARD_VERSION or "").strip()
    candidate = override or version_module.__version__
    return candidate if is_semver(candidate) else UNKNOWN
