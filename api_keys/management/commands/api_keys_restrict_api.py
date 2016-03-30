# This script is used to manage restricting access to this site's API through
# a Varnish-based api management system.

from django.core.management.base import BaseCommand
from django.conf import settings

from ...utils import redis_connection, RedisStrings


class Command(BaseCommand):
    help = """Restrict access the api named in settings.REDIS_API_NAME if
             settings.API_RESTRICT is True, un-restrict it otherwise."""

    def handle(self, **options):
        r = redis_connection()
        if settings.API_RESTRICT:
            r.set(RedisStrings.API_RESTRICT, '1')
            if options['verbosity'] > 1:
                self.stdout.write("Restricted api: {0}".format(settings.REDIS_API_NAME))
        else:
            r.delete(RedisStrings.API_RESTRICT)
            if options['verbosity'] > 1:
                self.stdout.write("Removed restriction on api: {0}".format(settings.REDIS_API_NAME))
