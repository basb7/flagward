from django.apps import AppConfig


class CoreFlagsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core_flags"

    def ready(self):
        # Imported for the side effect of connecting the change signals.
        from core_flags import signals  # noqa: F401
