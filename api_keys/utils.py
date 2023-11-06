import redis
from redis.sentinel import Sentinel

from django.conf import settings


_connection = None


def redis_connection():
    global _connection
    if _connection is None:
        if settings.REDIS_SENTINEL_HOSTS is not None:
            # If we have listed any sentinels, use those to manage the connection.
            # REDIS_SENTINEL_HOSTS will be a dict, but this needs an array of tuples [('host', port)]
            sentinel = Sentinel(
                [(host, port) for host, port in settings.REDIS_SENTINEL_HOSTS.items()],
                socket_timeout=0.1
            )
            _connection = sentinel.master_for(
                settings.REDIS_SENTINEL_SET,
                socket_timeout=0.1,
                db=settings.REDIS_DB_NUMBER,
                password=settings.REDIS_DB_PASSWORD
            )
        else:
            # Otherwise fall back to a regular connection
            _connection = redis.Redis(
                host=settings.REDIS_DB_HOST,
                port=settings.REDIS_DB_PORT,
                db=settings.REDIS_DB_NUMBER,
                password=settings.REDIS_DB_PASSWORD
            )
    return _connection


class RedisStrings(object):
    API_RESTRICT = 'api:{0}:restricted'.format(settings.REDIS_API_NAME)
    API_THROTTLE = 'api:{0}:throttled'.format(settings.REDIS_API_NAME)
    API_THROTTLE_COUNTER = 'api:{0}:counter:time'.format(settings.REDIS_API_NAME)
    API_THROTTLE_BLOCKED = 'api:{0}:blocked:time'.format(settings.REDIS_API_NAME)
    API_THROTTLE_DEFAULT_LIMIT = 'api:{0}:default_max'.format(settings.REDIS_API_NAME)
    API_QUOTA_DEFAULT_LIMIT = 'api:{0}:default_quota_limit'.format(settings.REDIS_API_NAME)

    @staticmethod
    def rate_limit_string(identity):
        return "key:{0}:ratelimit:{1}:max".format(identity, settings.REDIS_API_NAME)
