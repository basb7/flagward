"""
Tests for `telemetry.settings.is_enabled`, the single switch every telemetry
code path asks before touching the database or the network.

An explicit `FLAGWARD_TELEMETRY` always wins. Left unset, telemetry is on --
in production and development alike, so both kinds of install are counted --
except inside a CI run, which would otherwise report a throwaway install on
every pipeline. `DEBUG` deliberately plays no part: it only decides the
reported `mode`, never whether anything is sent.
"""
import pytest

from telemetry.settings import is_enabled


class TestIsEnabled:
    @pytest.mark.parametrize("raw", ["true", "1", "yes", "on", " TRUE "])
    def test_an_explicit_truthy_value_enables_even_in_ci(self, settings, raw):
        settings.FLAGWARD_TELEMETRY = raw
        settings.CI = True

        assert is_enabled() is True

    @pytest.mark.parametrize("raw", ["false", "0", "no", "off", " False "])
    def test_an_explicit_falsy_value_disables(self, settings, raw):
        settings.FLAGWARD_TELEMETRY = raw
        settings.CI = False

        assert is_enabled() is False

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_unset_or_empty_enables_outside_ci(self, settings, raw):
        settings.FLAGWARD_TELEMETRY = raw
        settings.CI = False

        assert is_enabled() is True

    @pytest.mark.parametrize("raw", [None, ""])
    def test_unset_or_empty_disables_inside_ci(self, settings, raw):
        settings.FLAGWARD_TELEMETRY = raw
        settings.CI = True

        assert is_enabled() is False

    def test_an_unrecognized_value_disables(self, settings):
        """A typo must never be read as consent to send."""
        settings.FLAGWARD_TELEMETRY = "maybe"
        settings.CI = False

        assert is_enabled() is False

    @pytest.mark.parametrize("debug", [True, False])
    def test_debug_does_not_affect_the_switch(self, settings, debug):
        settings.FLAGWARD_TELEMETRY = None
        settings.CI = False
        settings.DEBUG = debug

        assert is_enabled() is True


class TestTelemetryUrl:
    def test_reads_the_configured_url(self, settings):
        from telemetry.settings import telemetry_url

        settings.FLAGWARD_TELEMETRY_URL = "http://localhost:9999"

        assert telemetry_url() == "http://localhost:9999"

    @pytest.mark.parametrize("raw", ["", None])
    def test_an_empty_url_falls_back_to_the_default_collector(self, settings, raw):
        """compose forwards `${FLAGWARD_TELEMETRY_URL:-}`, which arrives as an empty string."""
        from telemetry.settings import DEFAULT_TELEMETRY_URL, telemetry_url

        settings.FLAGWARD_TELEMETRY_URL = raw

        assert telemetry_url() == DEFAULT_TELEMETRY_URL


class TestSuiteIsSilent:
    def test_the_test_suite_runs_with_telemetry_disabled(self):
        """Guard for tests/conftest.py: no test may reach the collector by default."""
        assert is_enabled() is False
