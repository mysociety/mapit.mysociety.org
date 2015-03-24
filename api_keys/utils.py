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

