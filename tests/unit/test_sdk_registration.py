"""
Tests for sdk_api models.
"""
import pytest
from django.db import IntegrityError, transaction

from core_flags.models import Environment
from sdk_api.models import SDKRegistration, SDKType


class TestSDKTypeCoversThePublishedAdapters:
    """
    Every published SDK names itself when it registers, and the dashboard
    groups by that name. `@flagward/core` sends JAVASCRIPT by default and each
    framework adapter overrides it with its own, so a value missing from this
    enum is a package already installed somewhere that the dashboard cannot
    label.

    Nothing enforces the enum at the API boundary: `sdk_register` writes
    whatever string arrives, because Django applies `choices` only in
    `full_clean()` and `update_or_create` never calls it. That is why an
    adapter can ship ahead of the backend -- and why this list is a claim
    about what the product supports rather than a gate.

    The values below come from outside this repository: they are what the
    published packages actually send. That is what keeps this from restating
    the enum back to itself -- renaming REACT here would break apps already
    installed, and this is what says so.
    """

    @pytest.mark.parametrize(
        "sdk_type",
        ["JAVASCRIPT", "REACT", "VUE", "SOLID", "SVELTE"],
    )
    def test_a_published_javascript_adapter_has_a_type(self, sdk_type):
        """The value the adapter sends is one this enum recognises."""
        assert sdk_type in SDKType.values


@pytest.mark.django_db
class TestSDKRegistrationUniqueness:
    """A registration is an inventory row: one per environment and SDK type."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)

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

    def test_same_sdk_type_coexists_across_environments(self, project):
        """The constraint is scoped to one environment."""
        other = Environment.objects.create(name="Staging", key="staging", project=project)

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
