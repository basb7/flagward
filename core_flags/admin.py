"""
Core flags admin configuration.
"""
from django.contrib import admin

from .models import Condition, Environment, FeatureFlag, FlagOverride, StrategyRule


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "api_key")
    search_fields = ("name", "key")
    readonly_fields = ("api_key",)

    def save_model(self, request, obj, form, change):
        if not obj.api_key:
            import uuid
            obj.api_key = str(uuid.uuid4()).replace("-", "")
        super().save_model(request, obj, form, change)


class ConditionInline(admin.TabularInline):
    model = Condition
    extra = 1


@admin.register(StrategyRule)
class StrategyRuleAdmin(admin.ModelAdmin):
    list_display = ("flag", "priority", "operator_logic")
    list_filter = ("operator_logic",)
    inlines = [ConditionInline]


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "environment", "is_enabled", "flag_type")
    list_filter = ("environment", "is_enabled", "flag_type")
    search_fields = ("key", "name")
    list_editable = ("is_enabled",)


@admin.register(Condition)
class ConditionAdmin(admin.ModelAdmin):
    list_display = ("rule", "attribute", "operator", "value")
    list_filter = ("operator",)


@admin.register(FlagOverride)
class FlagOverrideAdmin(admin.ModelAdmin):
    list_display = ("flag", "is_enabled", "is_active", "reason", "created_at", "cleared_at")
    # EmptyFieldListFilter reads as "active / lifted" instead of a date range.
    list_filter = ("is_enabled", ("cleared_at", admin.EmptyFieldListFilter))
    readonly_fields = ("created_at", "cleared_at")
