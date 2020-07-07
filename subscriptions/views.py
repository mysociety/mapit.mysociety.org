from __future__ import division

from datetime import datetime
import json
import smtplib

from django.conf import settings
from django.contrib import messages
from django.core import mail
from django.core.urlresolvers import reverse_lazy
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.views.generic import DetailView, FormView, DeleteView, View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponseRedirect, HttpResponse
import stripe

from mapit_mysociety_org.mixins import NeverCacheMixin
from .forms import SubsForm
from .models import Subscription


def add_vat(pence):
    """Add VAT and convert pounds to pence."""
    return round(pence * 1.2 / 100, 2)


class StripeObjectMixin(object):
    def get_object(self):
        try:
            sub = self.subscription = Subscription.objects.get(user=self.request.user)
            return stripe.Subscription.retrieve(sub.stripe_id, expand=[
                'customer.default_source', 'customer.invoice_settings.default_payment_method',
                'latest_invoice.payment_intent'])
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
        if data['discount'] and data['discount']['end']:
            data['discount']['end'] = datetime.fromtimestamp(data['discount']['end'])

        # Calculate actual amount paid, including discount
        if data['discount'] and data['discount']['coupon'] and data['discount']['coupon']['percent_off']:
            context['actual_paid'] = add_vat(int(
                data['plan']['amount'] * (100 - data['discount']['coupon']['percent_off']) / 100))
            data['plan']['amount'] = add_vat(data['plan']['amount'])
        else:
            data['plan']['amount'] = add_vat(data['plan']['amount'])
            context['actual_paid'] = data['plan']['amount']

        if data.customer.invoice_settings.default_payment_method:
            context['card_info'] = data.customer.invoice_settings.default_payment_method.card
        else:
            context['card_info'] = data.customer.default_source

        return context


class SubscriptionView(StripeObjectMixin, NeverCacheMixin, DetailView):
    model = Subscription
    context_object_name = 'stripe'
    needs_processing = None

    def get_template_names(self):
        if self.needs_processing:
            return ['subscriptions/check.html']
        else:
            return super(SubscriptionView, self).get_template_names()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        invoice = self.object and self.object.latest_invoice or None
        return self.process(invoice)

    def process(self, invoice):
        if invoice:
            self.check_payment_intent(invoice)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        sub = self.object = self.get_object()

        # Update source of customer
        payment_method = stripe.PaymentMethod.attach(request.POST['payment_method'], customer=sub.customer)
        stripe.Customer.modify(self.object.customer.id, invoice_settings={'default_payment_method': payment_method})

        try:
            invoice = stripe.Invoice.pay(sub.latest_invoice.id, expand=['payment_intent'])
        except stripe.error.CardError:  # pragma: no cover
            invoice = stripe.Invoice.retrieve(sub.latest_invoice.id, expand=['payment_intent'])

        return self.process(invoice)

    def get_context_data(self, **kwargs):
        context = super(SubscriptionView, self).get_context_data(**kwargs)
        context['STRIPE_PUBLIC_KEY'] = settings.STRIPE_PUBLIC_KEY
        if not self.object:
            return context
        if self.needs_processing is not None:
            context.update(self.needs_processing)
            return context
        else:
            return self.get_context_data_detail(**context)

    def get_context_data_detail(self, **context):
        customer = self.object.customer
        try:
            upcoming = stripe.Invoice.upcoming(customer=customer.id)
            upcoming['amount_due'] = upcoming['amount_due'] / 100
        except stripe.error.InvalidRequestError:
            upcoming = None

        balance = customer.account_balance
        if upcoming and upcoming.total < 0:
            # Going to be credited
            balance += upcoming.total

        context['account_balance'] = -balance / 100
        context['upcoming'] = upcoming
        context['quota_status'] = self.subscription.redis_status()
        return context

    def check_payment_intent(self, invoice):
        # The subscription has been created, but it is possible that the
        # payment failed (card error), or we need to do 3DS or similar
        pi = invoice.payment_intent
        if not pi:  # Free plan
            return

        if pi.status in ('requires_payment_method', 'requires_source'):
            self.needs_processing = {
                'requires_payment_method': True,
            }
        elif pi.status in ('requires_action', 'requires_source_action'):
            self.needs_processing = {
                'requires_action': True,
                'payment_intent_client_secret': pi.client_secret,
            }


class InvoicesView(StripeObjectMixin, NeverCacheMixin, DetailView):
    model = Subscription
    context_object_name = 'stripe'
    template_name = 'subscriptions/invoices.html'

    def get_context_data(self, **kwargs):
        context = super(InvoicesView, self).get_context_data(**kwargs)
        if not self.object:
            return context

        invoices = stripe.Invoice.list(subscription=self.object.id, limit=24)
        invoices = invoices.get('data', [])
        for invoice in invoices:
            if invoice['status_transitions']['finalized_at']:
                invoice['finalized_at'] = datetime.fromtimestamp(invoice['status_transitions']['finalized_at'])
            invoice['amount_due'] = invoice['amount_due'] / 100
        context['invoices'] = invoices

        return context


class SubscriptionUpdateMixin(object):
    def _update_subscription(self, form_data):
        if form_data['payment_method']:
            payment_method = stripe.PaymentMethod.attach(form_data['payment_method'], customer=self.object.customer.id)
            stripe.Customer.modify(
                self.object.customer.id, invoice_settings={'default_payment_method': payment_method})

        # Update Stripe subscription
        args = {
            'plan': form_data['plan'],
            'metadata': form_data['metadata'],
        }
        if form_data['coupon']:
            args['coupon'] = form_data['coupon']
        elif self.object.discount:
            args['coupon'] = ''
        stripe.Subscription.modify(self.object.id, payment_behavior='allow_incomplete', **args)

        # Attempt immediate payment on the upgrade
        try:
            invoice = stripe.Invoice.create(customer=self.object.customer, subscription=self.object, tax_percent=20)
            stripe.Invoice.finalize_invoice(invoice.id)
            stripe.Invoice.pay(invoice.id)
        except stripe.error.InvalidRequestError:
            pass  # No invoice created if nothing to pay
        except stripe.error.CardError:
            pass  # A source may still require 3DS... Stripe will have sent an email :-/

        return super(SubscriptionUpdateMixin, self).form_valid(form_data['form'])

    def _add_subscription(self, form_data):
        if hasattr(self.request.user, 'email'):
            email = self.request.user.email
        else:
            email = form_data['email'].strip()

        # Create new Stripe customer and subscription
        cust_params = {'email': email}
        if form_data['stripeToken']:
            cust_params['source'] = form_data['stripeToken']
        if form_data['payment_method']:
            cust_params['payment_method'] = form_data['payment_method']
            cust_params['invoice_settings'] = {'default_payment_method': form_data['payment_method']}
        obj = stripe.Customer.create(**cust_params)
        customer = obj.id

        assert form_data['stripeToken'] or form_data['payment_method'] or (
            form_data['plan'] == settings.PRICING[0]['plan'] and form_data['coupon'] == 'charitable100')
        obj = stripe.Subscription.create(
            payment_behavior='allow_incomplete',
            expand=['latest_invoice.payment_intent'],
            tax_percent=20,
            customer=customer, plan=form_data['plan'], coupon=form_data['coupon'], metadata=form_data['metadata'])
        stripe_id = obj.id

        # Now create the user (signup) or get redirect (update)
        try:
            resp = super(SubscriptionUpdateMixin, self).form_valid(form_data['form'])
        except smtplib.SMTPException:
            # A problem sending a confirmation email, don't fail out.
            resp = redirect(self.get_success_url())
        if hasattr(self, 'created_user'):
            user = self.created_user  # This now exists
        else:
            user = self.request.user
        self.subscription = Subscription.objects.create(user=user, stripe_id=stripe_id)
        return resp

    def update_subscription(self, form):
        form_data = form.cleaned_data
        form_data['form'] = form

        form_data['coupon'] = None
        if form_data['charitable'] in ('c', 'i'):
            form_data['coupon'] = 'charitable50'
            if form_data['plan'] == settings.PRICING[0]['plan']:
                form_data['coupon'] = 'charitable100'

        form_data['metadata'] = {
            'charitable': form_data['charitable'],
            'charity_number': form_data['charity_number'],
            'description': form_data['description'],
        }

        if hasattr(self, 'object') and self.object:
            resp = self._update_subscription(form_data)
        else:
            resp = self._add_subscription(form_data)

        messages.add_message(self.request, messages.INFO, 'Thank you very much!')
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
            initial['charitable_tick'] = True if self.object.discount else False
            initial['charitable'] = self.object.metadata.get('charitable', '')
            initial['charity_number'] = self.object.metadata.get('charity_number', '')
            initial['description'] = self.object.metadata.get('description', '')
        else:
            initial['plan'] = self.request.GET.get('plan')
        return initial

    def get_form_kwargs(self):
        kwargs = super(SubscriptionUpdateView, self).get_form_kwargs()
        kwargs['has_payment_data'] = self.object and (
            self.object.customer.default_source or self.object.customer.invoice_settings.default_payment_method)
        kwargs['stripe'] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        kwargs['STRIPE_PUBLIC_KEY'] = settings.STRIPE_PUBLIC_KEY
        kwargs['has_payment_data'] = self.object and (
            self.object.customer.default_source or self.object.customer.invoice_settings.default_payment_method)
        kwargs['stripe'] = self.object
        return super(SubscriptionUpdateView, self).get_context_data(**kwargs)

    def form_valid(self, form):
        return self.update_subscription(form)


class SubscriptionCardUpdateView(StripeObjectMixin, View):
    success_url = reverse_lazy('subscription')

    def get(self, request, *args, **kwargs):
        intent = stripe.SetupIntent.create()
        return HttpResponse(json.dumps({'secret': intent.client_secret}), content_type='application/json')

    def post(self, request, *args, **kwargs):
        sub = self.get_object()
        payment_method = request.POST['payment_method']
        payment_method = stripe.PaymentMethod.attach(payment_method, customer=sub.customer.id)
        stripe.Customer.modify(sub.customer.id, invoice_settings={'default_payment_method': payment_method})
        messages.add_message(self.request, messages.INFO, 'Your card details have been updated.')
        return HttpResponseRedirect(self.success_url)


class SubscriptionCancelView(StripeObjectMixin, DeleteView):
    template_name = 'subscriptions/cancel.html'
    success_url = reverse_lazy('subscription')

    def delete(self, request, *args, **kwargs):
        stripe_sub = self.get_object()
        if stripe_sub:
            stripe_sub.delete(at_period_end=True)
        messages.add_message(self.request, messages.INFO, 'Your subscription has been cancelled.')
        return HttpResponseRedirect(self.success_url)


def stripe_mapit_sub(invoice):
    # If the invoice doesn't have a subscription, ignore it
    if not invoice.subscription:
        return False
    stripe_sub = stripe.Subscription.retrieve(invoice.subscription)
    return stripe_sub.plan.id.startswith('mapit')


def stripe_reset_quota(subscription):
    try:
        sub = Subscription.objects.get(stripe_id=subscription)
        sub.redis_reset_quota()
    except Subscription.DoesNotExist:
        subject = "Someone's subscription was not renewed properly"
        message = "MapIt tried to reset the quota for subscription %s but couldn't find it" % subscription
        mail.EmailMessage(subject, message, to=[settings.CONTACT_EMAIL]).send()


@require_POST
@csrf_exempt
def stripe_hook(request):
    event_json = json.loads(request.body)
    event = stripe.Event.retrieve(event_json["id"])
    obj = event.data.object
    if event.type == 'customer.subscription.deleted':
        try:
            sub = Subscription.objects.get(stripe_id=obj.id)
            sub.delete()
        except Subscription.DoesNotExist:  # pragma: no cover
            pass
    elif event.type == 'customer.subscription.updated':
        try:
            sub = Subscription.objects.get(stripe_id=obj.id)
            sub.redis_update_max(obj.plan.id)
        except Subscription.DoesNotExist:  # pragma: no cover
            pass
    elif event.type == 'invoice.payment_failed' and obj.billing_reason == 'subscription_cycle' \
            and stripe_mapit_sub(obj):
        customer = stripe.Customer.retrieve(obj.customer)
        email = customer.email
        if obj.next_payment_attempt:
            subject = 'Your payment to MapIt has failed'
            message = render_to_string("subscriptions/email_payment_failed.txt", {})
            mail.EmailMessage(subject, message, to=[email]).send()
        else:
            subject = 'Your subscription to MapIt has been cancelled'
            message = render_to_string("subscriptions/email_cancelled.txt", {})
            mail.EmailMessage(subject, message, to=[email], bcc=[settings.CONTACT_EMAIL]).send()
    elif event.type == 'invoice.payment_succeeded' and stripe_mapit_sub(obj):
        # If this isn't a manual invoice (so it's the monthly one), reset the quota
        if obj.billing_reason != 'manual':
            stripe_reset_quota(obj.subscription)
        # The plan might have changed too, so update the maximum
        try:
            stripe_sub = stripe.Subscription.retrieve(obj.subscription)
            mapit_sub = Subscription.objects.get(stripe_id=obj.subscription)
            mapit_sub.redis_update_max(stripe_sub.plan.id)
        except Subscription.DoesNotExist:
            pass
        try:
            # Update the invoice's PaymentIntent and Charge to say it came from MapIt (for CSV export)
            # Both are shown in the Stripe admin, annoyingly
            if obj.payment_intent:
                stripe.PaymentIntent.modify(obj.payment_intent, description='MapIt')
            if obj.charge:
                stripe.Charge.modify(obj.charge, description='MapIt')
        except stripe.error.StripeError:  # pragma: no cover
            pass
    elif event.type == 'invoice.updated' and stripe_mapit_sub(obj):  # pragma: no branch
        previous = getattr(event.data, 'previous_attributes', None)
        if obj.forgiven and previous and 'forgiven' in previous and not previous['forgiven']:
            stripe_reset_quota(obj.subscription)
    return HttpResponse(status=200)
