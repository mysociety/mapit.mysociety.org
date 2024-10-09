from __future__ import division

from datetime import datetime
import json
import smtplib

from django.conf import settings
from django.contrib import messages
from django.core import mail
from django.urls import reverse_lazy
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
            sub_stripe = stripe.Subscription.retrieve(sub.stripe_id, expand=[
                'customer.default_source', 'customer.invoice_settings.default_payment_method',
                'latest_invoice.payment_intent', 'schedule.phases.items.price'])
        except Subscription.DoesNotExist:
            # There will be existing accounts with no subscription object
            return None
        except stripe.error.InvalidRequestError:
            # If the subscription is missing at the Stripe end, assume it's
            # gone and remove here too
            sub.delete()
            return None
        # Make a helper to the price
        sub_stripe.price = sub_stripe['items'].data[0].price
        return sub_stripe

    def get_context_data(self, **kwargs):
        context = super(StripeObjectMixin, self).get_context_data(**kwargs)
        if not self.object:
            return context

        data = self.object
        for fld in ['current_period_start', 'current_period_end', 'created', 'start_date']:
            data[fld] = datetime.fromtimestamp(data[fld])
        if data['discount'] and data['discount']['end']:
            data['discount']['end'] = datetime.fromtimestamp(data['discount']['end'])

        # Calculate actual amount paid, including discount
        if data['discount'] and data['discount']['coupon'] and data['discount']['coupon']['percent_off']:
            context['actual_paid'] = add_vat(int(
                data['price']['unit_amount'] * (100 - data['discount']['coupon']['percent_off']) / 100))
            data['price']['unit_amount'] = add_vat(data['price']['unit_amount'])
        else:
            data['price']['unit_amount'] = add_vat(data['price']['unit_amount'])
            context['actual_paid'] = data['price']['unit_amount']

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

        balance = customer.balance
        if upcoming and upcoming.total < 0:
            # Going to be credited
            balance += upcoming.total

        context['balance'] = -balance / 100
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

        for p in settings.PRICING:
            if p['id'] == form_data['price']:
                new_price = p['price'] * 100
                if form_data['coupon'] == 'charitable100':
                    new_price = 0
                elif form_data['coupon'] == 'charitable50':
                    new_price /= 2
            if p['id'] == self.object.price.id:
                old_price = p['price'] * 100
                if self.object.discount and (coupon := self.object.discount.coupon):
                    if coupon.percent_off == 100:
                        old_price = 0
                    elif coupon.percent_off == 50:
                        old_price /= 2

        if old_price >= new_price:
            if self.object.schedule:
                stripe.SubscriptionSchedule.release(self.object.schedule)
            schedule = stripe.SubscriptionSchedule.create(from_subscription=self.object.id)
            phases = [
                {
                    'items': [{'price': schedule.phases[0]['items'][0].price}],
                    'start_date': schedule.phases[0].start_date,
                    'end_date': schedule.phases[0].end_date,
                    'proration_behavior': 'none',
                    'default_tax_rates': [settings.STRIPE_TAX_RATE],
                },
                {
                    'items': [{'price': form_data['price']}],
                    'iterations': 1,
                    'metadata': form_data['metadata'],
                    'proration_behavior': 'none',
                    'default_tax_rates': [settings.STRIPE_TAX_RATE],
                },
            ]
            if schedule.phases[0].discounts and schedule.phases[0].discounts[0].coupon:
                phases[0]['discounts'] = [{'coupon': schedule.phases[0].discounts[0].coupon}]
            if form_data['coupon']:
                phases[1]['coupon'] = form_data['coupon']
            stripe.SubscriptionSchedule.modify(schedule.id, phases=phases)
            messages.add_message(
                self.request, messages.INFO, 'Your subscription will downgrade '
                'at the end of your current billing period.')

        if old_price < new_price:
            args = {
                'items': [{'price': form_data['price']}],
                'metadata': form_data['metadata'],
                'cancel_at_period_end': False,  # just in case it had been cancelled
                'payment_behavior': 'allow_incomplete',
                'proration_behavior': 'always_invoice',
            }
            if form_data['coupon']:
                args['coupon'] = form_data['coupon']
            elif self.object.discount:
                args['coupon'] = ''
            if self.object.schedule:
                stripe.SubscriptionSchedule.release(self.object.schedule)
            stripe.Subscription.modify(self.object.id, **args)

            messages.add_message(self.request, messages.INFO, 'Thank you very much!')

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

        # At the point the customer is created, details such as postcode and
        # security code can be checked, and therefore fail
        try:
            obj = stripe.Customer.create(**cust_params)
        except (stripe.error.CardError, stripe.error.InvalidRequestError) as e:
            message = 'Sorry, we could not process your payment, please try again.'
            if hasattr(e, 'user_message'):
                message += f' Our payment processor returned: {e.user_message}'
            form = form_data['form']
            form.add_error(None, message)
            # So the token clears
            form.add_error('stripeToken', message)
            return super(SubscriptionUpdateMixin, self).form_invalid(form)
        customer = obj.id

        assert form_data['stripeToken'] or form_data['payment_method'] or (
            form_data['price'] == settings.PRICING[0]['id'] and form_data['coupon'] == 'charitable100')
        obj = stripe.Subscription.create(
            payment_behavior='allow_incomplete',
            expand=['latest_invoice.payment_intent'],
            default_tax_rates=[settings.STRIPE_TAX_RATE],
            customer=customer,
            items=[{"price": form_data['price']}],
            coupon=form_data['coupon'],
            metadata=form_data['metadata'])
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
            if form_data['price'] == settings.PRICING[0]['id']:
                form_data['coupon'] = 'charitable100'

        form_data['metadata'] = {
            'charitable': form_data['charitable'],
            'charity_number': form_data['charity_number'],
            'description': form_data['description'],
            'interest_contact': form_data['interest_contact'] and 'Yes' or 'No',
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
            interest_contact = self.object.metadata.get('interest_contact', 'No')
            interest_contact = interest_contact == 'Yes' and True or False
            initial['price'] = self.object.price.id
            initial['charitable_tick'] = True if self.object.discount else False
            initial['charitable'] = self.object.metadata.get('charitable', '')
            initial['charity_number'] = self.object.metadata.get('charity_number', '')
            initial['description'] = self.object.metadata.get('description', '')
            initial['interest_contact'] = interest_contact
        else:
            initial['price'] = self.request.GET.get('price')
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
        intent = stripe.SetupIntent.create(
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )
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

    def form_valid(self, form):
        if self.object:
            if self.object.schedule:
                stripe.SubscriptionSchedule.release(self.object.schedule)
            stripe.Subscription.modify(self.object.id, cancel_at_period_end=True)
        messages.add_message(self.request, messages.INFO, 'Your subscription has been cancelled.')
        return HttpResponseRedirect(self.success_url)


def stripe_mapit_sub(invoice):
    # If the invoice doesn't have a subscription, ignore it
    if not invoice.subscription:
        return False
    stripe_sub = stripe.Subscription.retrieve(invoice.subscription, expand=['items.data.price.product'])
    return stripe_sub['items'].data[0].price.product.name.startswith('MapIt')


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
            sub.redis_update_max(obj['items'].data[0].price)
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
            mapit_sub.redis_update_max(stripe_sub['items'].data[0].price)
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
        if obj.status == 'uncollectible' and previous and 'status' in previous \
                and previous['status'] != 'uncollectible':
            stripe_reset_quota(obj.subscription)
    return HttpResponse(status=200)
