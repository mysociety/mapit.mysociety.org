from django.conf import settings


def contact_email(request):
    return {'CONTACT_EMAIL': settings.CONTACT_EMAIL}
