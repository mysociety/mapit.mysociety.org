from django.conf import settings


def add_settings(request):
    return {
        'CONTACT_EMAIL': settings.CONTACT_EMAIL,
        'PRICING': settings.PRICING,
        'BULK_LOOKUP_AMOUNT': settings.BULK_LOOKUP_AMOUNT,
        'STRIPE_PUBLIC_KEY': settings.STRIPE_PUBLIC_KEY,
        'STRIPE_API_VERSION': settings.STRIPE_API_VERSION,
    }
