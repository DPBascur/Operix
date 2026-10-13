from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "occurred_at", "event_type", "rule_id", "rule_version", "zone_id")
    list_filter = ("event_type", "rule_id", "zone_id")
    search_fields = ("id", "rule_id", "zone_id", "view_id")
    readonly_fields = tuple(field.name for field in Event._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
