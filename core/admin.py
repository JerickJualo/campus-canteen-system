from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action_type', 'user', 'target', 'description')
    list_filter = ('action_type', 'created_at')
    search_fields = ('description', 'target', 'user__username')

# Register your models here.
