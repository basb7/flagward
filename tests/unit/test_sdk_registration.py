"""
Tests for sdk_api models.
"""
import pytest
from django.db import IntegrityError, transaction

from core_flags.models import Environment
from sdk_api.models import SDKRegistration, SDKType


@pytest.mark.django_db
class TestSDKRegistrationUniqueness:
    """A registration is an inventory row: one per environment and SDK type."""

    def setup_method(self):
        self.env = Environment.objects.create(name="Prod", key="prod")

    def test_duplicate_environment_and_sdk_type_is_rejected(self):
        """The database refuses a second row for the same environment and type."""
        SDKRegistration.objects.create(
            environment=self.env, sdk_type=SDKType.JAVASCRIPT, version="1.0.0"
        )

        with pytest.raises(IntegrityError):
            SDKRegistration.objects.create(
                environment=self.env, sdk_type=SDKType.JAVASCRIPT, version="1.0.1"
            )

    def test_different_sdk_types_coexist_in_one_environment(self):
        """The constraint must not collapse distinct SDK types."""
        SDKRegistration.objects.create(
            environment=self.env, sdk_type=SDKType.JAVASCRIPT, version="1.0.0"
        )
        SDKRegistration.objects.create(
            environment=self.env, sdk_type=SDKType.PYTHON, version="1.0.0"
        )

        assert SDKRegistration.objects.filter(environment=self.env).count() == 2

    def test_same_sdk_type_coexists_across_environments(self):
        """The constraint is scoped to one environment."""
        other = Environment.objects.create(name="Staging", key="staging")

        SDKRegistration.objects.create(
            environment=self.env, sdk_type=SDKType.JAVASCRIPT, version="1.0.0"
        )
        SDKRegistration.objects.create(
            environment=other, sdk_type=SDKType.JAVASCRIPT, version="1.0.0"
        )

        assert SDKRegistration.objects.count() == 2

    def test_update_or_create_recovers_from_a_concurrent_insert(self):
        """
        update_or_create catches the IntegrityError a losing race raises and
        falls back to reading the winner's row. That recovery only runs when the
        database enforces uniqueness, which is what this constraint provides.
        """
        winner = SDKRegistration.objects.create(
            environment=self.env, sdk_type=SDKType.JAVASCRIPT, version="1.0.0"
        )

        with transaction.atomic():
            registration, created = SDKRegistration.objects.update_or_create(
                environment=self.env,
                sdk_type=SDKType.JAVASCRIPT,
                defaults={"version": "1.0.1"},
            )

        assert created is False
        assert registration.pk == winner.pk
        assert registration.version == "1.0.1"
        assert SDKRegistration.objects.count() == 1
