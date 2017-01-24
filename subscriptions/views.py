from __future__ import division

from datetime import datetime
import smtplib

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse_lazy
from django.shortcuts import redirect
from django.views.generic import DetailView, FormView
import stripe

from mapit_mysociety_org.mixins import NeverCacheMixin
from .forms import SubsForm
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
        if hasattr(self.request.user, 'email'):
            email = self.request.user.email
        else:
            email = form_data['email'].strip()

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

        if hasattr(self, 'object') and self.object:
            if form_data['stripeToken']:
                self.object.customer.source = form_data['stripeToken']
                self.object.customer.save()

            # Update Stripe subscription
            self.object.plan = form_data['plan']
            if coupon:
                self.object.coupon = coupon
            elif self.object.discount:
                self.object.delete_discount()
            self.object.metadata = metadata
            self.object.save()
            return super(SubscriptionUpdateMixin, self).form_valid(form)
        else:
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
            if hasattr(self, 'created_user'):
                user = self.created_user  # This now exists
            else:
                user = self.request.user

            Subscription.objects.create(user=user, stripe_id=stripe_id)

            return resp


class SubscriptionUpdateView(StripeObjectMixin, SubscriptionUpdateMixin, NeverCacheMixin, FormView):
    form_class = SubsForm
    template_name = 'subscriptions/update.html'
    success_url = reverse_lazy('subscription')

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(SubscriptionUpdateView, self).dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super(SubscriptionUpdateView, self).get_initial()
        if self.object:
            initial['plan'] = self.object.plan.id
            initial['charitable_tick'] = self.object.discount
            initial['charitable'] = self.object.metadata.get('charitable', '')
            initial['charity_number'] = self.object.metadata.get('charity_number', '')
            initial['description'] = self.object.metadata.get('description', '')
        return initial

    def get_form_kwargs(self):
        kwargs = super(SubscriptionUpdateView, self).get_form_kwargs()
        kwargs['has_payment_data'] = self.object and self.object.customer.default_source
        kwargs['stripe'] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        kwargs['STRIPE_PUBLIC_KEY'] = settings.STRIPE_PUBLIC_KEY
        kwargs['has_payment_data'] = self.object and self.object.customer.default_source
        kwargs['stripe'] = self.object
        return super(SubscriptionUpdateView, self).get_context_data(**kwargs)

    def form_valid(self, form):
        resp = self.update_subscription(form)
        messages.add_message(self.request, messages.INFO, 'Thank you very much!')
        return resp
