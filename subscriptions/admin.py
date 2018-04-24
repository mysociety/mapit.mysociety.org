from django.contrib import admin

from .models import Subscription


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('stripe_id', 'user')
    search_fields = ('user__email',)


admin.site.register(Subscription, SubscriptionAdmin)
