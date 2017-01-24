from __future__ import division

from datetime import datetime
import smtplib

from django.conf import settings
from django.shortcuts import redirect
from django.views.generic import DetailView
import stripe

from mapit_mysociety_org.mixins import NeverCacheMixin
from .models import Subscription


class StripeObjectMixin(object):
    def get_object(self):
        try:
            sub = self.subscription = Subscription.objects.get(user=self.request.user)
            return stripe.Subscription.retrieve(sub.stripe_id, expand=['customer.default_source'])
        except Subscription.DoesNotExist:
            # There will be existing accounts with no subscription object
            return None
        except stripe.error.InvalidRequestError:
            # If the subscription is missing at the Stripe end, assume it's
            # gone and remove here too
            sub.delete()
            return None

    def get_context_data(self, **kwargs):
        context = super(StripeObjectMixin, self).get_context_data(**kwargs)
        if not self.object:
            return context

        data = self.object
        for fld in ['current_period_start', 'current_period_end', 'created', 'start']:
            data[fld] = datetime.fromtimestamp(data[fld])

        # Amounts in pounds, not pence
        data['plan']['amount'] /= 100

        # Calculate actual amount paid, including discount
        if data['discount'] and data['discount']['coupon'] and data['discount']['coupon']['percent_off']:
            context['actual_paid'] = data['plan']['amount'] * (100 - data['discount']['coupon']['percent_off']) / 100
        else:
            context['actual_paid'] = data['plan']['amount']

        return context


class SubscriptionView(StripeObjectMixin, NeverCacheMixin, DetailView):
    model = Subscription
    context_object_name = 'stripe'


class SubscriptionUpdateMixin(object):
    def update_subscription(self, form):
        form_data = form.cleaned_data
        email = form.cleaned_data["email"].strip()

        coupon = None
        if form_data['charitable'] in ('c', 'i'):
            coupon = 'charitable50'
            if form_data['plan'] == settings.PRICING[0]['plan']:
                coupon = 'charitable100'

        metadata = {
            'charitable': form_data['charitable'],
            'charity_number': form_data['charity_number'],
            'description': form_data['description'],
        }

        cust_params = {'email': email}
        if form_data['stripeToken']:
            cust_params['source'] = form_data['stripeToken']
        obj = stripe.Customer.create(**cust_params)
        customer = obj.id

        assert form_data['stripeToken'] or (
            form_data['plan'] == settings.PRICING[0]['plan'] and coupon == 'charitable100')
        obj = stripe.Subscription.create(
            customer=customer, plan=form_data['plan'], coupon=coupon, metadata=metadata)
        stripe_id = obj.id

        # Now create the user (signup) or get redirect (update)
        try:
            resp = super(SubscriptionUpdateMixin, self).form_valid(form)
        except smtplib.SMTPException:
            # A problem sending a confirmation email, don't fail out.
            resp = redirect(self.get_success_url())
        user = self.created_user  # This now exists
        Subscription.objects.create(user=user, stripe_id=stripe_id)

        return resp
