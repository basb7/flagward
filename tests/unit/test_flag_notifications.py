"""
Tests for the change notifications the SSE stream waits on.
"""
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from core_flags.models import (
    Condition,
    ConditionOperator,
    Environment,
    FeatureFlag,
    FlagOverride,
    StrategyRule,
)
from core_flags.notifications import (
    asubscribe_to_flags,
    channel_for,
    is_available,
    publish_flags_changed,
)

PUBLISH = "core_flags.signals.publish_flags_changed"


class TestChannel:
    def test_channel_is_scoped_to_one_environment(self):
        """A client must not be woken by changes in someone else's environment."""
        assert channel_for("env-a") != channel_for("env-b")

    def test_channel_is_stable_for_the_same_environment(self):
        """Publisher and subscriber have to agree without sharing state."""
        assert channel_for("env-a") == channel_for("env-a")


class TestDegradingWithoutRedis:
    """
    REDIS_URL is optional, so every deployment without it has to keep working:
    the stream falls back to polling and nothing raises.
    """

    def test_availability_follows_the_configured_url(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert is_available() is False

    def test_publishing_without_redis_is_a_no_op(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert publish_flags_changed("env-a") is False

    def test_publishing_to_an_unreachable_redis_does_not_raise(self, monkeypatch):
        """A broken cache must never break saving a flag."""
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:65535/0")
        assert publish_flags_changed("env-a") is False


@pytest.mark.django_db
class TestChangesArePublished:
    """
    Anything that alters what an SDK would evaluate has to wake the stream,
    whether it was changed through the API, the admin or a shell.
    """

    def setup_method(self):
        self.env = Environment.objects.create(name="Prod", key="prod")

    def make_flag(self):
        return FeatureFlag.objects.create(
            environment=self.env, key="beta", name="Beta", is_enabled=True
        )

    def test_creating_a_flag_publishes(self):
        with patch(PUBLISH) as publish:
            self.make_flag()

        publish.assert_called_with(self.env.id)

    def test_updating_a_flag_publishes(self):
        flag = self.make_flag()

        with patch(PUBLISH) as publish:
            flag.is_enabled = False
            flag.save()

        publish.assert_called_with(self.env.id)

    def test_deleting_a_flag_publishes(self):
        flag = self.make_flag()

        with patch(PUBLISH) as publish:
            flag.delete()

        publish.assert_called_with(self.env.id)

    def test_a_rule_change_publishes_for_its_environment(self):
        flag = self.make_flag()

        with patch(PUBLISH) as publish:
            StrategyRule.objects.create(flag=flag, priority=1, operator_logic="AND")

        publish.assert_called_with(self.env.id)

    def test_a_condition_change_publishes_for_its_environment(self):
        flag = self.make_flag()
        rule = StrategyRule.objects.create(flag=flag, priority=1, operator_logic="AND")

        with patch(PUBLISH) as publish:
            Condition.objects.create(
                rule=rule,
                attribute="plan",
                operator=ConditionOperator.EQUALS,
                value="pro",
            )

        publish.assert_called_with(self.env.id)

    def test_an_override_publishes_for_its_environment(self):
        """Overrides are the incident path: they must propagate immediately."""
        flag = self.make_flag()

        with patch(PUBLISH) as publish:
            FlagOverride.objects.create(flag=flag, is_enabled=False, reason="incident")

        publish.assert_called_with(self.env.id)


class TestSignalsAreWiredByTheApp:
    """
    Patching a name in core_flags.signals imports that module, and importing it
    connects the receivers as a side effect. Every test above therefore passes
    even when the app never wires them, and production would publish nothing.

    Checking the wiring means checking a process where nothing but Django's own
    startup has imported that module, so this runs one.
    """

    def connected_receivers(self) -> set[str]:
        """Receiver names connected after a bare django.setup(), nothing else."""
        script = textwrap.dedent(
            """
            import os, weakref
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
            import django
            django.setup()
            from django.db.models.signals import post_delete, post_save

            names = set()
            for signal, kind in ((post_save, "save"), (post_delete, "delete")):
                for entry in signal.receivers:
                    receiver = entry[1]
                    func = receiver() if isinstance(receiver, weakref.ref) else receiver
                    if func is not None and getattr(func, "__name__", None):
                        names.add(f"{kind}:{func.__name__}")
            print(",".join(sorted(names)))
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
            check=True,
        )
        return set(result.stdout.strip().split(","))

    def test_every_model_that_changes_a_payload_is_wired_at_startup(self):
        connected = self.connected_receivers()

        assert {
            "save:flag_changed",
            "save:rule_changed",
            "save:condition_changed",
            "save:override_changed",
            "delete:flag_changed",
            "delete:rule_changed",
            "delete:condition_changed",
            "delete:override_changed",
        } <= connected


class TestAsyncSubscriptionDegrades:
    """The stream is async, so its subscription has to degrade the same way."""

    @pytest.mark.asyncio
    async def test_no_subscription_without_redis(self, monkeypatch):
        """Returning None is what makes the stream fall back to polling."""
        monkeypatch.delenv("REDIS_URL", raising=False)

        assert await asubscribe_to_flags("env-a") is None

    @pytest.mark.asyncio
    async def test_an_unreachable_redis_does_not_raise(self, monkeypatch):
        """A broken cache degrades the stream, it does not break the request."""
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:65535/0")

        assert await asubscribe_to_flags("env-a") is None
