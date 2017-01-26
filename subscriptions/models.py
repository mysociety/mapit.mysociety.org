import re

from django.conf import settings
from django.db import models
from django.dispatch import receiver

from api_keys.utils import redis_connection


class Subscription(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_id = models.CharField(max_length=100)

    def __unicode__(self):
        return u"%s (%s)" % (self.user, self.stripe_id)

    @property
    def redis_key(self):
        return "user:{0}:quota:{1}".format(self.user.id, settings.REDIS_API_NAME)

    @property
    def redis_key_count(self):
        return "{0}:count".format(self.redis_key)

    @property
    def redis_key_max(self):
        return "{0}:max".format(self.redis_key)

    @property
    def redis_key_blocked(self):
        return "{0}:blocked".format(self.redis_key)

    def redis_update_max(self, plan):
        m = re.match('mapit-(\d+)k', plan)
        max = int(m.group(1)) * 1000
        r = redis_connection()
        r.set(self.redis_key_max, max)
        r.delete(self.redis_key_blocked)

    def redis_reset_quota(self):
        r = redis_connection()
        r.delete(self.redis_key_count)
        r.delete(self.redis_key_blocked)

    def delete_from_redis(self):
        r = redis_connection()
        r.delete(self.redis_key_max)
        r.delete(self.redis_key_count)
        r.delete(self.redis_key_blocked)


@receiver(models.signals.pre_delete)
def delete_subscription_from_redis(sender, instance, using, **kwargs):
    if sender == Subscription:
        instance.delete_from_redis()
