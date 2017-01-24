import smtplib

from django.conf import settings
from django.shortcuts import redirect
import stripe

from .models import Subscription


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
