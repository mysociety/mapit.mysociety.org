# This script is used to manage the default quota level through a Varnish-based
# api management system.

from django.core.management.base import BaseCommand
from django.conf import settings

from api_keys.utils import redis_connection, RedisStrings


class Command(BaseCommand):
    help = """Set the default quota level (per key or IP address) for the API
        named in settings.REDIS_API_NAME."""

    def handle(self, **options):
        r = redis_connection()
        r.set(RedisStrings.API_QUOTA_DEFAULT_LIMIT, settings.API_QUOTA_DEFAULT_LIMIT)
        if options['verbosity'] > 1:
            self.stdout.write("Set {0} API quota default limit to {1}".format(
                settings.REDIS_API_NAME,
                settings.API_QUOTA_DEFAULT_LIMIT))

        # Respect any clients that are excluded from quotas
        for identity in settings.API_THROTTLE_UNLIMITED:
            key = "user:{0}:quota:{1}:max".format(identity, settings.REDIS_API_NAME)
            r.set(key, '0')
            if options['verbosity'] > 1:
                self.stdout.write("Excluded {0} from quota".format(identity))
