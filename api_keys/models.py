import string
import random

from django.db import models
from django.dispatch import receiver
from django.conf import settings

from six import python_2_unicode_compatible
from account.signals import user_signed_up

from .utils import redis_connection


# Inspired by https://github.com/CIGIHub/django-simple-api-key
@python_2_unicode_compatible
class APIKey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='api_key',
        on_delete=models.CASCADE
    )
    key = models.CharField(max_length=40, blank=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return u"%s: %s" % (self.user, self.key)

    def save(self, *args, **kwargs):
        # Call the "real" save() method.
        super(APIKey, self).save(*args, **kwargs)

        self.save_key_to_redis()

    @property
    def redis_key(self):
        return "key:{0}:api:{1}".format(self.key, settings.REDIS_API_NAME)

    @property
    def redis_key_quota(self):
        return "key:{0}:quota:{1}:count".format(self.key, settings.REDIS_API_NAME)

    @property
    def usage_count(self):
        r = redis_connection()
        return r.get(self.redis_key_quota)

    def save_key_to_redis(self):
        r = redis_connection()
        r.set(self.redis_key, self.user.id)

    def delete_key_from_redis(self):
        r = redis_connection()
        r.delete(self.redis_key)
        r.delete(self.redis_key_quota)

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


@receiver(models.signals.pre_delete)
def delete_api_key_from_redis(sender, instance, using, **kwargs):
    """Delete an APIKey from redis when it's deleted."""
    if sender == APIKey:
        instance.delete_key_from_redis()
