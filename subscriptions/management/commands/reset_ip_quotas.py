from django.core.management.base import BaseCommand
from django.conf import settings

from api_keys.utils import redis_connection


class Command(BaseCommand):
    help = """Reset IP address daily usage blocks."""

    def handle(self, **options):
        r = redis_connection()
        # Clear IPv4 and IPv6 separately due to issues with our test mock handling a glob in the match.
        # IPv4
        for key in r.scan_iter(match='user:*.*:quota:%s:count' % settings.REDIS_API_NAME, count=100):
            r.delete(key)
            if options['verbosity'] > 1:
                self.stdout.write("Removed IP %s" % key)
        for key in r.scan_iter(match='user:*.*:quota:%s:blocked' % settings.REDIS_API_NAME, count=100):
            r.delete(key)
        # IPv6
        for key in r.scan_iter(match='user:*:*:quota:%s:count' % settings.REDIS_API_NAME, count=100):
            r.delete(key)
            if options['verbosity'] > 1:
                self.stdout.write("Removed IP %s" % key)
        for key in r.scan_iter(match='user:*:*:quota:%s:blocked' % settings.REDIS_API_NAME, count=100):
            r.delete(key)
