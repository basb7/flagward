"""
Publish a notification whenever an environment's flags change.

Hooked on the models rather than on the API views on purpose: a flag can also be
changed from the admin, a management command or a shell, and an SDK that missed
those would serve a stale value with no indication anything was wrong.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core_flags.models import Condition, FeatureFlag, FlagOverride, StrategyRule
from core_flags.notifications import publish_flags_changed


@receiver(post_save, sender=FeatureFlag)
@receiver(post_delete, sender=FeatureFlag)
def flag_changed(instance, **kwargs):
    publish_flags_changed(instance.environment_id)


@receiver(post_save, sender=StrategyRule)
@receiver(post_delete, sender=StrategyRule)
def rule_changed(instance, **kwargs):
    publish_flags_changed(instance.flag.environment_id)


@receiver(post_save, sender=Condition)
@receiver(post_delete, sender=Condition)
def condition_changed(instance, **kwargs):
    publish_flags_changed(instance.rule.flag.environment_id)


@receiver(post_save, sender=FlagOverride)
@receiver(post_delete, sender=FlagOverride)
def override_changed(instance, **kwargs):
    publish_flags_changed(instance.flag.environment_id)
