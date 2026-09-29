"""
Telemetry state for this installation.
"""
import uuid

from django.db import models
from django.utils import timezone

SINGLETON_ID = 1


class InstallationIdentity(models.Model):
    """
    The single row identifying this installation to the telemetry collector.

    `installation_id` is a random UUID4, never derived from SECRET_KEY, a
    hostname or any user data. `last_sent_at` is the daily send slot: a worker
    only sends after atomically moving it forward (see telemetry.runtime).
    """
    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_ID, editable=False)
    installation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    first_seen_at = models.DateTimeField(default=timezone.now, editable=False)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=SINGLETON_ID),
                name="installation_identity_is_a_singleton",
            ),
        ]

    def __str__(self):
        return f"Installation {self.installation_id}"

    @classmethod
    def get_or_create_singleton(cls) -> "InstallationIdentity":
        # get_or_create retries the read on IntegrityError, so two workers
        # racing on a fresh database still end up with the same row.
        identity, _ = cls.objects.get_or_create(id=SINGLETON_ID)
        return identity
