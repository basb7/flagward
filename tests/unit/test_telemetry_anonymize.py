"""
Tests for `telemetry.anonymize`: the mappings that turn client-controlled or
fingerprintable values into coarse, safe ones before they leave the install.

`SDKRegistration.sdk_type` and `version` are free text sent by SDKs
(`sdk_register` never validates them), so both are mapped against an
allowlist. Evaluation volume is sent as a bucket, never as an exact count.
"""
import pytest

from telemetry.anonymize import evaluation_bucket, plan_name, sdk_type_name, sdk_version


class TestSdkTypeName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("REACT", "react"),
            ("react", "react"),
            ("JavaScript", "javascript"),
            ("SVELTE", "svelte"),
        ],
    )
    def test_a_known_type_is_reported_lowercased(self, raw, expected):
        assert sdk_type_name(raw) == expected

    @pytest.mark.parametrize("raw", ["my-internal-thing", "", None, "REACT-acme"])
    def test_an_unknown_type_is_other(self, raw):
        assert sdk_type_name(raw) == "other"


class TestSdkVersion:
    @pytest.mark.parametrize("raw", ["0.4.0", "1.2.3-beta.1", "2.0.0+build.5"])
    def test_a_semver_version_is_kept(self, raw):
        assert sdk_version(raw) == raw

    @pytest.mark.parametrize("raw", ["build-acme-42", "latest", "", None, "1.2"])
    def test_a_non_semver_version_is_unknown(self, raw):
        assert sdk_version(raw) == "unknown"


class TestPlanName:
    def test_a_known_plan_is_kept(self):
        assert plan_name("COMMUNITY") == "COMMUNITY"

    def test_an_unknown_plan_is_other(self):
        assert plan_name("ACME-ENTERPRISE-DEAL") == "other"


class TestEvaluationBucket:
    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (0, "0"),
            (1, "1-100"),
            (99, "1-100"),
            (100, "100-1k"),
            (999, "100-1k"),
            (1000, "1k-10k"),
            (4321, "1k-10k"),
            (10_000, "10k-100k"),
            (99_999, "10k-100k"),
            (100_000, "100k+"),
            (5_000_000, "100k+"),
        ],
    )
    def test_counts_map_to_half_open_buckets(self, count, expected):
        assert evaluation_bucket(count) == expected
