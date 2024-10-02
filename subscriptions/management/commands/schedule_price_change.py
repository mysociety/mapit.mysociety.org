from django.conf import settings
from django.core.management.base import BaseCommand
import stripe

from subscriptions.models import Subscription

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


class Command(BaseCommand):
    help = "Update subscriptions on one Stripe Price to a different Price"

    def add_arguments(self, parser):
        prices = stripe.Price.list(limit=100, expand=['data.product'])
        price_ids = [price.id for price in prices if price.product.name.startswith('MapIt')]
        parser.add_argument('--old-price', choices=price_ids, required=True)
        parser.add_argument('--new-price', choices=price_ids, required=True)
        parser.add_argument('--commit', action='store_true')

    def new_schedule(self, subscription, new_price):
        schedule = stripe.SubscriptionSchedule.create(from_subscription=subscription.id)
        phases = [
            {
                'items': [{'price': schedule.phases[0]['items'][0].price}],
                'start_date': schedule.phases[0].start_date,
                'iterations': 2,
                'proration_behavior': 'none',
                'default_tax_rates': [settings.STRIPE_TAX_RATE],
            },
            {
                'items': [{'price': new_price}],
                'iterations': 1,
                'proration_behavior': 'none',
                'default_tax_rates': [settings.STRIPE_TAX_RATE],
            },
        ]
        # Maintain current discount, if any
        if schedule.phases[0].discounts and schedule.phases[0].discounts[0].coupon:
            phases[0]['discounts'] = [{'coupon': schedule.phases[0].discounts[0].coupon}]
            phases[1]['discounts'] = [{'coupon': schedule.phases[0].discounts[0].coupon}]
        stripe.SubscriptionSchedule.modify(schedule.id, phases=phases)

    def handle(self, *args, **options):
        old_price = options['old_price']
        new_price = options['new_price']

        for sub_obj in Subscription.objects.all():
            subscription = stripe.Subscription.retrieve(sub_obj.stripe_id, expand=[
                'schedule.phases.items.price', 'discounts'])
            if subscription.discounts and subscription.discounts[0].coupon.id == 'charitable100':
                # Ignore free subscriptions
                continue
            if subscription.status != 'active':
                # Ignore non-active subscriptions
                continue

            # Possibilities:
            # * No schedule, just a monthly plan
            # * 3 phases: This script has already been run on this subscription - nothing to do
            # * 2 phases: Asked for a downgrade, so either in first phase
            #   current price, then new price, then no schedule; or is already
            #   at new price in second phase
            # * 2 phases: Already on 'new price' schedule, awaiting change - nothing to do
            sub_info = f"{subscription.id} {sub_obj.user.email}"
            if subscription.schedule:
                schedule = subscription.schedule
                if len(schedule.phases) > 2:
                    self.stdout.write(f"{sub_info} has {len(schedule.phases)} phases, assume processed already")
                elif len(schedule.phases) == 2:
                    if schedule.phases[1]['items'][0].price.id != old_price:
                        continue
                    if schedule.current_phase.start_date == schedule.phases[1].start_date:
                        # In phase 2
                        self.stdout.write(f"{sub_info} has two phases, in latter, start new schedule")
                        if options['commit']:
                            stripe.SubscriptionSchedule.release(schedule)
                            self.new_schedule(subscription, new_price)
                    else:
                        # In phase 1
                        phases = [
                            {
                                'items': [{'price': schedule.phases[0]['items'][0].price.id}],
                                'start_date': schedule.phases[0].start_date,
                                'end_date': schedule.phases[0].end_date,
                                'proration_behavior': 'none',
                                'default_tax_rates': [settings.STRIPE_TAX_RATE],
                            },
                            {
                                'items': [{'price': schedule.phases[1]['items'][0].price.id}],
                                'start_date': schedule.phases[1].start_date,
                                'end_date': schedule.phases[1].end_date,
                                'proration_behavior': 'none',
                                'default_tax_rates': [settings.STRIPE_TAX_RATE],
                            },
                            {
                                'items': [{'price': new_price}],
                                'iterations': 1,
                                'proration_behavior': 'none',
                                'default_tax_rates': [settings.STRIPE_TAX_RATE],
                            },
                        ]
                        # Maintain current discount, if any
                        if schedule.phases[0].discounts and schedule.phases[0].discounts[0].coupon:
                            phases[0]['discounts'] = [{'coupon': schedule.phases[0].discounts[0].coupon}]
                        if schedule.phases[1].discounts and schedule.phases[1].discounts[0].coupon:
                            phases[1]['discounts'] = [{'coupon': schedule.phases[1].discounts[0].coupon}]
                            phases[2]['discounts'] = [{'coupon': schedule.phases[1].discounts[0].coupon}]
                        self.stdout.write(f"{sub_info} has two phases, adding third phase to new price")
                        if options['commit']:
                            stripe.SubscriptionSchedule.modify(schedule.id, phases=phases)
                else:
                    self.stdout.write(f"{sub_info} has {len(schedule.phases)} phases, something odd!")
            else:
                if subscription['items'].data[0].price.id != old_price:
                    continue
                self.stdout.write(f"{sub_info} has no phase, adding schedule to new price")
                if options['commit']:
                    self.new_schedule(subscription, new_price)
