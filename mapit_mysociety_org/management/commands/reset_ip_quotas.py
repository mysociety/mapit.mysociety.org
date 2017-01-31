from django.core.management.base import BaseCommand
from django.conf import settings

from api_keys.utils import redis_connection


def redis_set(r, key):
    val = r.spop(key)
    while val:
        yield val
        val = r.spop(key)


class Command(BaseCommand):
    help = """Reset IP address daily usage blocks."""

    def handle(self, **options):
        r = redis_connection()
        key = 'api:%s:blocked_ips' % settings.REDIS_API_NAME
        for ip in redis_set(r, key):
            r.delete('user:%s:quota:%s:blocked' % (ip, settings.REDIS_API_NAME))
            r.delete('user:%s:quota:%s:count' % (ip, settings.REDIS_API_NAME))
            if options['verbosity'] > 1:
                self.stdout.write("Removed IP %s" % ip)
