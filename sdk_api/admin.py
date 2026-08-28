"""
SDK API admin configuration.
"""
from django.contrib import admin

from .models import EvaluationLog, SDKRegistration


@admin.register(SDKRegistration)
class SDKRegistrationAdmin(admin.ModelAdmin):
    list_display = ("sdk_type", "sdk_key", "environment", "version", "last_seen_at", "created_at")
    list_filter = ("sdk_type", "environment")
    search_fields = ("sdk_key",)
    readonly_fields = ("last_seen_at", "created_at")


@admin.register(EvaluationLog)
class EvaluationLogAdmin(admin.ModelAdmin):
    list_display = ("flag", "context_hash", "result", "timestamp")
    list_filter = ("result",)
    readonly_fields = ("timestamp",)
