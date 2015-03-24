# This script is used to manage throttling access to this site's API through
# a Varnish-based api management system.

from django.core.management.base import NoArgsCommand
from django.conf import settings

from ...utils import redis_connection, RedisStrings

class Command(NoArgsCommand):
    help = """Throttle access to the api named in settings.REDIS_API_NAME if
            settings.API_THROTTLE is True, un-throttle it otherwise."""

    def handle_noargs(self, **options):
        r = redis_connection()
        r = redis_connection()
        if settings.API_THROTTLE:
            r.set(RedisStrings.API_THROTTLE, '1')
            r.set(RedisStrings.API_THROTTLE_COUNTER, settings.API_THROTTLE_COUNTER)
            r.set(RedisStrings.API_THROTTLE_BLOCKED, settings.API_THROTTLE_BLOCKED)
            r.set(RedisStrings.API_THROTTLE_DEFAULT_LIMIT, settings.API_THROTTLE_DEFAULT_LIMIT)
            if options['verbosity'] > 2:
                self.stdout.write("Throttled api: {0}".format(settings.REDIS_API_NAME))
                self.stdout.write("Set throttling to {0} hits in {1} seconds, blocking offenders for {2} seconds.".format(settings.API_THROTTLE_DEFAULT_LIMIT, settings.API_THROTTLE_COUNTER, settings.API_THROTTLE_BLOCKED))
        else:
            r.delete(RedisStrings.API_THROTTLE)
            r.delete(RedisStrings.API_THROTTLE_COUNTER)
            r.delete(RedisStrings.API_THROTTLE_BLOCKED)
            r.delete(RedisStrings.API_THROTTLE_DEFAULT_LIMIT)
            if options['verbosity'] > 2:
                self.stdout.write("Removed throttling on api: {0}".format(settings.REDIS_API_NAME))
