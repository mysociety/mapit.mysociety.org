from django.conf import settings


def add_settings(request):
    return {
        'CONTACT_EMAIL': settings.CONTACT_EMAIL,
        'PRICING': settings.PRICING,
    }
