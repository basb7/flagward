"""
Tests for `InstallationIdentity`, the one row that says "this is the same
installation as yesterday".

The ID is a random UUID4 persisted in the database -- never derived from
SECRET_KEY, a hostname or anything else that could be reversed or correlated.
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from telemetry.models import InstallationIdentity


@pytest.mark.django_db
class TestGetOrCreateSingleton:
    def test_the_first_call_creates_the_identity(self):
        before = timezone.now()

        identity = InstallationIdentity.get_or_create_singleton()

        assert InstallationIdentity.objects.count() == 1
        assert isinstance(identity.installation_id, uuid.UUID)
        assert identity.installation_id.version == 4
        assert identity.first_seen_at >= before
        assert identity.last_sent_at is None

    def test_later_calls_return_the_same_identity(self):
        first = InstallationIdentity.get_or_create_singleton()

        second = InstallationIdentity.get_or_create_singleton()

        assert InstallationIdentity.objects.count() == 1
        assert second.installation_id == first.installation_id
        assert second.first_seen_at == first.first_seen_at

    def test_an_existing_identity_is_never_overwritten(self):
        seen = timezone.now() - timedelta(days=30)
        existing = InstallationIdentity.get_or_create_singleton()
        InstallationIdentity.objects.filter(pk=existing.pk).update(first_seen_at=seen)

        identity = InstallationIdentity.get_or_create_singleton()

        assert identity.installation_id == existing.installation_id
        assert identity.first_seen_at == seen

    def test_each_installation_gets_its_own_random_id(self):
        first = InstallationIdentity.get_or_create_singleton()
        InstallationIdentity.objects.all().delete()

        second = InstallationIdentity.get_or_create_singleton()

        assert second.installation_id != first.installation_id
