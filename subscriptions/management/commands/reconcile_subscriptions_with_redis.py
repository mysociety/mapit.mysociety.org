import re

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand

from api_keys.utils import redis_connection
from subscriptions.models import Subscription

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


class Command(BaseCommand):
    help = """Ensure subscription quota information in Redis is up to date
        i.e. maxes are up to date and only set for entitled users."""

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Run for real.")

    def lookup_stripe_sub_and_process(self, sub, commit):
        try:
            stripe_sub = stripe.Subscription.retrieve(sub.stripe_id)
        except Exception as e:  # pragma: no cover
            self.stdout.write(
                f"  Unable to query Stripe with error below; skipping.\n  {e}"
            )
            return

        if stripe_sub.status == "canceled":
            self.stdout.write(
                "  Stripe sub is cancelled; will delete sub from DB and quota from redis (if present)."
            )
            if commit:
                sub.delete()
                self.stdout.write(
                    "  Sub deleted and quota deleted from redis (if was present)."
                )
            return

        if stripe_sub.status == "active" or stripe_sub.status == "past_due":
            self.stdout.write(
                f"  Stripe sub status is '{stripe_sub.status}'; will ensure max is set correctly."
            )
            if commit:
                sub.redis_update_max(stripe_sub["items"].data[0].price, unblock=False)
                self.stdout.write("  Sub max set.")
            return

        self.stdout.write(
            f"  Stripe sub was in unexpected state {stripe_sub.status}; skipping."
        )

    def handle(self, **options):
        r = redis_connection()

        commit = options["commit"]
        if not commit:  # pragma: no cover
            self.stdout.write("Runing in dry mode. No changes will be made.")

        self.stdout.write("==== Looking at quotas currently set in Redis")
        self.stdout.write()

        user_re = re.compile(f"user:([^:]+):quota:{settings.REDIS_API_NAME}:max")
        user_quota_maxes_in_redis = {}
        for k in r.scan_iter(
            match="user:*:quota:%s:max" % settings.REDIS_API_NAME, count=100
        ):
            k = k.decode("utf-8")
            m = user_re.match(k)
            if not m:
                continue
            uid = m.group(1)
            if not uid.isnumeric():
                continue
            user_quota_maxes_in_redis[uid] = k

        self.stdout.write(
            f"There are currently {len(user_quota_maxes_in_redis)} user quotas set up in redis."
        )

        for uid, max_quota_redis_key in user_quota_maxes_in_redis.items():
            self.stdout.write()
            self.stdout.write(f"  Looking at quota for user {uid}.")

            try:
                sub = Subscription.objects.get(user_id=uid)
            except Subscription.DoesNotExist:
                self.stdout.write(
                    "  No sub in DB for this quota; will delete from redis."
                )
                if commit:
                    Subscription.delete_from_redis_for_user_id(uid)
                    self.stdout.write("  Quota deleted from redis.")
                continue
            self.stdout.write(f"  Associated Stripe sub ID is {sub.stripe_id}.")

            self.lookup_stripe_sub_and_process(sub, commit)

        self.stdout.write()
        self.stdout.write("==== Looking at subs in the DB with no quota in Redis")
        self.stdout.write()

        subs_not_in_redis = Subscription.objects.exclude(
            user_id__in=user_quota_maxes_in_redis.keys()
        )
        self.stdout.write(
            f"There are {len(subs_not_in_redis)} subs in the DB with no quota in redis."
        )

        for sub in subs_not_in_redis:
            self.stdout.write()
            self.stdout.write(
                f"  Looking at sub with Stripe ID {sub.stripe_id} for user {uid}."
            )
            self.lookup_stripe_sub_and_process(sub, commit)
