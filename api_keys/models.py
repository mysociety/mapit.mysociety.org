import string
import random

from django.db import models
from django.dispatch import receiver
from django.conf import settings

from account.signals import user_signed_up


# Inspired by https://github.com/CIGIHub/django-simple-api-key
class APIKey(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='api_key')
    key = models.CharField(max_length=40, blank=False, unique=True)

    def __unicode__(self):
        return "%s: %s" % (self.user, self.key)

    @staticmethod
    def generate_key(size=40, chars=string.ascii_letters + string.digits):
        return ''.join(random.choice(chars) for x in range(size))


@receiver(user_signed_up)
def create_key_for_new_user(user, form, **kwargs):
    """Create a new APIKey for a user who just signed up."""

    # If there was a key already for them (who know's, it could happen) we
    # delete it, assuming that the user account system has responsibility for
    # making sure the account should exist.
    try:
        key = APIKey.objects.get(user=user)
        key.delete()
    except APIKey.DoesNotExist:
        pass

    APIKey.objects.create(user=user, key=APIKey.generate_key())

