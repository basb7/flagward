"""
Core flag models for the feature flag system.
"""
import uuid

from django.db import models
from django.utils import timezone


class FlagType(models.TextChoices):
    """Flag type enumeration."""
    BOOLEAN = "BOOLEAN", "Boolean"
    MULTIVARIATE = "MULTIVARIATE", "Multivariate"


class OperatorLogic(models.TextChoices):
    """Operator logic for strategy rules."""
    AND = "AND", "And"
    OR = "OR", "Or"


class ConditionOperator(models.TextChoices):
    """Operators for conditions."""
    EQUALS = "EQUALS", "Equals"
    NOT_EQUALS = "NOT_EQUALS", "Not Equals"
    GREATER_THAN = "GREATER_THAN", "Greater Than"
    LESS_THAN = "LESS_THAN", "Less Than"
    IN_LIST = "IN_LIST", "In List"
    CONTAINS = "CONTAINS", "Contains"


class Environment(models.Model):
    """Environment model for feature flags."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("tenancy.Project", on_delete=models.CASCADE, related_name="environments")
    name = models.CharField(max_length=255)
    key = models.SlugField(max_length=255)
    api_key = models.CharField(max_length=255, unique=True, db_index=True)

    class Meta:
        unique_together = ("project", "key")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = str(uuid.uuid4()).replace("-", "")
        super().save(*args, **kwargs)


class FeatureFlag(models.Model):
    """Feature flag model."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name="flags")
    key = models.SlugField(max_length=255)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_enabled = models.BooleanField(default=False)
    flag_type = models.CharField(
        max_length=20,
        choices=FlagType.choices,
        default=FlagType.BOOLEAN,
    )

    class Meta:
        unique_together = ("environment", "key")
        ordering = ["key"]

    def __str__(self):
        return f"{self.environment.key}/{self.key}"


class StrategyRule(models.Model):
    """Strategy rule for feature flag evaluation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flag = models.ForeignKey(FeatureFlag, on_delete=models.CASCADE, related_name="rules")
    priority = models.IntegerField(default=0)
    operator_logic = models.CharField(
        max_length=3,
        choices=OperatorLogic.choices,
        default=OperatorLogic.AND,
    )

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return f"Rule {self.priority} for {self.flag}"


class Condition(models.Model):
    """Condition for strategy rule evaluation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(StrategyRule, on_delete=models.CASCADE, related_name="conditions")
    attribute = models.CharField(max_length=255)
    operator = models.CharField(
        max_length=20,
        choices=ConditionOperator.choices,
    )
    value = models.JSONField()

    def __str__(self):
        return f"{self.attribute} {self.operator} {self.value}"


class FlagOverrideQuerySet(models.QuerySet):
    """Queryset helpers for reading override state."""

    def active(self):
        """Overrides that have not been lifted."""
        return self.filter(cleared_at__isnull=True)

    def active_for(self, flag):
        """The override currently forcing `flag`, or None."""
        return self.active().filter(flag=flag).order_by("-created_at").first()


class FlagOverride(models.Model):
    """
    A forced value for a flag, used as a kill switch.

    While active, an override wins over the flag's own `is_enabled` and bypasses
    targeting rules. It never rewrites the flag's configuration, so lifting it
    returns the flag to the state it was configured with.

    Rows are never deleted: lifting one stamps `cleared_at` and keeps the trail
    of who forced what and why.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flag = models.ForeignKey(FeatureFlag, on_delete=models.CASCADE, related_name="overrides")
    is_enabled = models.BooleanField()
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    cleared_at = models.DateTimeField(null=True, blank=True)

    objects = FlagOverrideQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["flag", "cleared_at"]),
        ]

    def __str__(self):
        return f"Override for {self.flag}"

    @property
    def is_active(self) -> bool:
        """Whether this override is still forcing the flag."""
        return self.cleared_at is None

    def lift(self):
        """Stop forcing the flag. Lifting an already-lifted override is a no-op."""
        if self.cleared_at is not None:
            return
        self.cleared_at = timezone.now()
        self.save(update_fields=["cleared_at"])
