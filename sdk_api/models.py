"""
SDK models for tracking SDK registrations and evaluations.
"""
import uuid

from django.db import models

from core_flags.models import Environment, FeatureFlag


class SDKType(models.TextChoices):
    """SDK type enumeration."""
    PYTHON = "PYTHON", "Python"
    JAVASCRIPT = "JAVASCRIPT", "JavaScript"
    GO = "GO", "Go"


class SDKRegistration(models.Model):
    """SDK registration model."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name="sdk_registrations")
    sdk_key = models.CharField(max_length=255, unique=True, db_index=True)
    sdk_type = models.CharField(
        max_length=20,
        choices=SDKType.choices,
    )
    version = models.CharField(max_length=50)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # A registration is an inventory row, not one row per running
            # instance: every client sharing an environment's API key updates
            # the same row. Without this, two concurrent registrations both
            # insert, and update_or_create then fails permanently with
            # MultipleObjectsReturned.
            models.UniqueConstraint(
                fields=["environment", "sdk_type"],
                name="unique_sdk_registration_per_environment_and_type",
            ),
        ]

    def __str__(self):
        return f"{self.sdk_type} SDK ({self.sdk_key})"

    def save(self, *args, **kwargs):
        if not self.sdk_key:
            self.sdk_key = str(uuid.uuid4()).replace("-", "")
        super().save(*args, **kwargs)


class EvaluationLog(models.Model):
    """Evaluation log model for analytics."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flag = models.ForeignKey(FeatureFlag, on_delete=models.CASCADE, related_name="evaluation_logs")
    context_hash = models.CharField(max_length=64)
    result = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Evaluation of {self.flag} at {self.timestamp}"
