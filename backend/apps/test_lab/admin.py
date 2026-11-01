from django.contrib import admin

from .models import CaseResult, Fixture, TestRun


@admin.register(Fixture)
class FixtureAdmin(admin.ModelAdmin):
    list_display = ("name", "module", "builtin_key", "input_type", "active", "updated_at")
    list_filter = ("module", "active", "input_type")
    search_fields = ("name",)


class CaseInline(admin.TabularInline):
    model = CaseResult
    extra = 0
    fields = ("fixture_name", "module", "outcome", "change", "duration_ms")
    readonly_fields = fields
    can_delete = False


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = ("reference", "status", "total", "passed", "failed", "errors", "created_by", "created_at")
    list_filter = ("status",)
    inlines = [CaseInline]
