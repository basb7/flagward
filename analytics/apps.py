"""
Analytics app configuration.
"""
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Aggregation endpoints over flags, SDKs and evaluation logs. Holds no models."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'
