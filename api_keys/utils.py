import redis

from django.conf import settings


_connection = None

def redis_connection():
    global _connection
    if _connection is None:
        _connection = redis.StrictRedis(
            host=settings.REDIS_DB_HOST,
            port=settings.REDIS_DB_PORT,
            db=settings.REDIS_DB_NUMBER,
            password=settings.REDIS_DB_PASSWORD
        )
    return _connection

class RedisStrings(object):
    API_RESTRICT = 'api:{0}:restricted'.format(settings.REDIS_API_NAME)
    API_THROTTLE = 'api:{0}:restricted'.format(settings.REDIS_API_NAME)
    API_THROTTLE_COUNTER = 'api:{0}:counter'.format(settings.REDIS_API_NAME)
    API_THROTTLE_BLOCKED = 'api:{0}:blocked'.format(settings.REDIS_API_NAME)
    API_THROTTLE_DEFAULT_LIMIT = 'api:{0}:default_max'.format(settings.REDIS_API_NAME)

    @staticmethod
    def rate_limit_string(identity):
        return "key:{0}:usage:{1}:max".format(identity, settings.REDIS_API_NAME)

