"""
Tests for `config.settings.env_base_url`, the helper backing
`FRONTEND_BASE_URL` (see config/settings.py). Kept separate from the
`env_flag`/`env_list` helpers it sits beside because it has its own contract:
a base URL gets joined with a path to build a clickable link, so trailing
whitespace and a trailing slash must not survive into that join as a doubled
slash -- and, matching this file's existing permissive stance on `EMAIL_HOST`
and `CORS_ALLOWED_ORIGINS`, a malformed value is not rejected, only passed
through unchanged.
"""
import os

from config.settings import env_base_url


class TestEnvBaseUrl:
    def test_uses_the_default_when_the_variable_is_unset(self):
        os.environ.pop("DOES_NOT_EXIST_FRONTEND_BASE_URL", None)

        assert env_base_url("DOES_NOT_EXIST_FRONTEND_BASE_URL", "http://localhost:3000") == "http://localhost:3000"

    def test_strips_a_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com/")

        assert env_base_url("FRONTEND_BASE_URL", "http://localhost:3000") == "https://app.example.com"

    def test_strips_multiple_trailing_slashes(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com///")

        assert env_base_url("FRONTEND_BASE_URL", "http://localhost:3000") == "https://app.example.com"

    def test_strips_surrounding_whitespace(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_BASE_URL", "  https://app.example.com  ")

        assert env_base_url("FRONTEND_BASE_URL", "http://localhost:3000") == "https://app.example.com"

    def test_a_malformed_value_is_passed_through_unchanged_rather_than_rejected(self, monkeypatch):
        """
        No scheme validation happens here, deliberately: this module never
        validates `EMAIL_HOST` or `CORS_ALLOWED_ORIGINS` either, so rejecting
        only this one env var would be an inconsistent surprise. A malformed
        value produces a malformed (but honest, non-crashing) link instead.
        """
        monkeypatch.setenv("FRONTEND_BASE_URL", "not-a-url")

        assert env_base_url("FRONTEND_BASE_URL", "http://localhost:3000") == "not-a-url"
