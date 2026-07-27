import re

from django.conf import settings
from django.core.management.base import BaseCommand
from more_itertools import batched

from api_keys.utils import redis_connection
from api_keys.models import APIKey


class Command(BaseCommand):
    help = """Ensure API key information in Redis is up to date
        i.e. only ones in the DB are set."""

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Run for real.")

    def handle(self, **options):
        r = redis_connection()

        commit = options["commit"]
        if not commit:  # pragma: no cover
            self.stdout.write("Runing in dry mode. No changes will be made.")
            self.stdout.write("")

        key_re = re.compile(f"key:([^:]+):api:{settings.REDIS_API_NAME}")
        to_delete = set()
        for redis_keys in batched(
            r.scan_iter(match="key:*:api:%s" % settings.REDIS_API_NAME, count=100), 100
        ):
            key_map = {
                k: key_re.match(k).group(1)
                for k in [r.decode("utf-8") for r in redis_keys]
            }
            in_db = APIKey.objects.filter(key__in=key_map.values()).values_list(
                "key", flat=True
            )
            not_in_db = {r for r, a in key_map.items() if a not in in_db}
            to_delete.update(not_in_db)

        self.stdout.write(f"Found {len(to_delete)} API keys in Redis to delete.")
        if commit and to_delete:
            r.delete(*to_delete)
            self.stdout.write("Keys deleted.")

        total_keys = APIKey.objects.all().count()
        self.stdout.write(f"{total_keys} API keys to ensure are in Redis.")

        if commit:
            for keys in batched(APIKey.objects.all(), 100):
                mapping = {k.redis_key: k.user.id for k in keys}
                r.mset(mapping)
            self.stdout.write("Keys set.")
