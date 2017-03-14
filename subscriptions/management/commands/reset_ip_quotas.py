from django.core.management.base import BaseCommand
from django.conf import settings

from api_keys.utils import redis_connection


class Command(BaseCommand):
    help = """Reset IP address daily usage blocks."""

    def handle(self, **options):
        r = redis_connection()
        for key in r.scan_iter(match='user:*.*:quota:%s:count' % settings.REDIS_API_NAME, count=100):
            r.delete(key)
            if options['verbosity'] > 1:
                self.stdout.write("Removed IP %s" % key)
        for key in r.scan_iter(match='user:*.*:quota:%s:blocked' % settings.REDIS_API_NAME, count=100):
            r.delete(key)
