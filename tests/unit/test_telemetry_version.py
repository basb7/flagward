"""
Tests for `telemetry.version.get_version`.

Operators build the image from source through `compose.yml`, so the version
lives in code (`config/version.py`) rather than in a Docker build argument.
`FLAGWARD_VERSION` overrides it, and anything that is not semver is reported
as "unknown" instead of being sent as free text.
"""
import pytest

from config import version as version_module
from telemetry.version import get_version


class TestGetVersion:
    def test_returns_the_code_version(self, settings, monkeypatch):
        settings.FLAGWARD_VERSION = None
        monkeypatch.setattr(version_module, "__version__", "0.6.0")

        assert get_version() == "0.6.0"

    def test_the_environment_override_wins(self, settings, monkeypatch):
        settings.FLAGWARD_VERSION = "0.6.1-rc1"
        monkeypatch.setattr(version_module, "__version__", "0.6.0")

        assert get_version() == "0.6.1-rc1"

    def test_an_empty_override_falls_back_to_the_code_version(self, settings, monkeypatch):
        settings.FLAGWARD_VERSION = "  "
        monkeypatch.setattr(version_module, "__version__", "0.6.0")

        assert get_version() == "0.6.0"

    @pytest.mark.parametrize("raw", ["", "latest", "build-acme-42", "v0.6.0", "0.6"])
    def test_a_non_semver_version_is_unknown(self, settings, monkeypatch, raw):
        settings.FLAGWARD_VERSION = None
        monkeypatch.setattr(version_module, "__version__", raw)

        assert get_version() == "unknown"

    def test_a_non_semver_override_is_unknown(self, settings, monkeypatch):
        settings.FLAGWARD_VERSION = "acme-internal"
        monkeypatch.setattr(version_module, "__version__", "0.6.0")

        assert get_version() == "unknown"

    def test_the_shipped_version_is_semver(self, settings):
        settings.FLAGWARD_VERSION = None

        assert get_version() != "unknown"
