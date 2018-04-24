from django.contrib import admin

from .models import APIKey


class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('key', 'user', 'created_at')
    search_fields = ('user__email',)


admin.site.register(APIKey, APIKeyAdmin)
