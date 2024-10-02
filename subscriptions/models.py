import re

from django.conf import settings
from django.db import models
from django.dispatch import receiver

from api_keys.utils import redis_connection


def ensure_int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


class Subscription(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_id = models.CharField(max_length=100)

    def __str__(self):
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

    @property
    def redis_key_history(self):
        return "{0}:history".format(self.redis_key)

    def redis_update_max(self, price):
        m = re.match(r'mapit-(\d+)k', price)
        max = int(m.group(1)) * 1000
        r = redis_connection()
        r.set(self.redis_key_max, max)
        r.delete(self.redis_key_blocked)

    def redis_reset_quota(self):
        r = redis_connection()
        count = r.getset(self.redis_key_count, 0)
        if count is not None:
            r.rpush(self.redis_key_history, count)
        r.delete(self.redis_key_blocked)

    def delete_from_redis(self):
        r = redis_connection()
        r.delete(self.redis_key_max)
        r.delete(self.redis_key_count)
        r.delete(self.redis_key_blocked)

    def redis_status(self):
        r = redis_connection()
        return {
            'count': ensure_int(r.get(self.redis_key_count)),
            'blocked': ensure_int(r.get(self.redis_key_blocked)),
            'quota': ensure_int(r.get(self.redis_key_max)),
            'history': r.lrange(self.redis_key_history, 0, -1),
        }


@receiver(models.signals.pre_delete)
def delete_subscription_from_redis(sender, instance, using, **kwargs):
    if sender == Subscription:
        instance.delete_from_redis()
