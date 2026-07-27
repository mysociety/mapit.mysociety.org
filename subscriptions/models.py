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

    @classmethod
    def redis_key_for_user_id(cls, uid):
        return "user:{0}:quota:{1}".format(uid, settings.REDIS_API_NAME)

    @classmethod
    def redis_key_count_for_user_id(cls, uid):
        return "{0}:count".format(cls.redis_key_for_user_id(uid))

    @classmethod
    def redis_key_max_for_user_id(cls, uid):
        return "{0}:max".format(cls.redis_key_for_user_id(uid))

    @classmethod
    def redis_key_blocked_for_user_id(cls, uid):
        return "{0}:blocked".format(cls.redis_key_for_user_id(uid))

    @classmethod
    def redis_key_history_for_user_id(cls, uid):
        return "{0}:history".format(cls.redis_key_for_user_id(uid))

    @classmethod
    def delete_from_redis_for_user_id(cls, uid):
        r = redis_connection()
        r.delete(cls.redis_key_max_for_user_id(uid))
        r.delete(cls.redis_key_count_for_user_id(uid))
        r.delete(cls.redis_key_blocked_for_user_id(uid))

    @property
    def redis_key(self):
        return self.redis_key_for_user_id(self.user.id)

    @property
    def redis_key_count(self):
        return self.redis_key_count_for_user_id(self.user.id)

    @property
    def redis_key_max(self):
        return self.redis_key_max_for_user_id(self.user.id)

    @property
    def redis_key_blocked(self):
        return self.redis_key_blocked_for_user_id(self.user.id)

    @property
    def redis_key_history(self):
        return self.redis_key_history_for_user_id(self.user.id)

    def redis_update_max(self, price, unblock=True):
        max = int(price.metadata['calls'])
        r = redis_connection()
        r.set(self.redis_key_max, max)
        if unblock:
            r.delete(self.redis_key_blocked)

    def redis_reset_quota(self):
        r = redis_connection()
        count = r.getset(self.redis_key_count, 0)
        if count is not None:
            r.rpush(self.redis_key_history, count)
        r.delete(self.redis_key_blocked)

    def delete_from_redis(self):
        self.delete_from_redis_for_user_id(self.user.id)

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
