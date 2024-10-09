# encoding: utf-8

import json
from io import StringIO
import time
from mock import patch, Mock, ANY

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.test import TestCase
from django.test.utils import override_settings
import stripe
from stripe import convert_to_stripe_object

from api_keys.tests import PatchedRedisTestCase
from api_keys.utils import redis_connection
from subscriptions.models import Subscription
from subscriptions.forms import SubsForm


class UserTestCase(PatchedRedisTestCase):
    def setUp(self):
        super(UserTestCase, self).setUp()
        self.user = User.objects.create_user("Test user", "test@example.com", "password")

    def tearDown(self):
        self.user.delete()
        super(UserTestCase, self).tearDown()


class PatchedStripeMixin(object):
    """Patch Stripe calls so that create() return IDs and retrieve() returns
    an unlimited 50%-off subscription."""
    def setUp(self):
        super(PatchedStripeMixin, self).setUp()
        patcher = patch('subscriptions.views.stripe')
        self.MockStripe = patcher.start()
        self.MockStripe.Subscription.retrieve.return_value = convert_to_stripe_object({
            'id': 'SUBSCRIPTION-ID',
            'created': time.time(),
            'start_date': time.time(),
            'current_period_start': time.time(),
            'current_period_end': time.time(),
            'cancel_at_period_end': False,
            'discount': {
                'coupon': {
                    'percent_off': 50.0,
                },
                'end': time.time(),
            },
            'latest_invoice': None,
            'metadata': {
                'charitable': 'c',
                'charity_number': 123,
            },
            'customer': {
                'id': 'CUSTOMER-ID',
                'email': 'CUSTOMER-EMAIL',
                'balance': -400,
                'default_source': {'brand': 'Visa', 'last4': '1234'},
                'invoice_settings': {'default_payment_method': None},
                'save': Mock(),
            },
            'items': {
                'data': [{
                    'price': {
                        'id': 'price_789',
                        'nickname': 'MapIt, unlimited calls',
                        'unit_amount': 25000,
                        'metadata': {
                            'calls': '0',
                        },
                        'product': {
                            'id': 'prod_ABC',
                            'name': 'MapIt, unlimited calls',
                        },
                    },
                }],
            },
            "schedule": None,
        }, None, None)
        self.MockStripe.Customer.create.return_value = convert_to_stripe_object({
            'id': 'CUSTOMER-ID'
        }, None, None)
        self.MockStripe.Customer.retrieve.return_value = convert_to_stripe_object({
            'id': 'CUSTOMER-ID',
            'email': 'customer@example.net',
        }, None, None)
        self.MockStripe.Subscription.create.return_value = convert_to_stripe_object({
            'id': 'SUBSCRIPTION-ID-CREATE'
        }, None, None)
        self.MockStripe.SubscriptionSchedule.create.return_value = convert_to_stripe_object({
            'id': 'SCHEDULE-ID',
            'phases': [{
                'start_date': time.time(),
                'end_date': time.time(),
                'discounts': [{
                    'coupon': 'charitable50',
                }],
                'items': [{
                    'price': 'price_789',
                }]
            }],
        }, None, None)
        self.MockStripe.Invoice.create.return_value = convert_to_stripe_object({
            'id': 'INVOICE-CREATE'
        }, None, None)
        self.MockStripe.Invoice.upcoming.return_value = convert_to_stripe_object({
            'id': 'INVOICE',
            'amount_due': 15000,
            'total': 15000,
        }, None, None)
        self.MockStripe.Invoice.list.return_value = convert_to_stripe_object({
            'data': [{
                'number': 'INVOICE-002',
                'amount_due': 2000,
                'status_transitions': {'finalized_at': time.time()},
                'status': 'open',
            }, {
                'number': 'INVOICE-001',
                'amount_due': 2000,
                'status_transitions': {'finalized_at': time.time()},
                'status': 'paid',
                'invoice_pdf': 'https://example.org/pdf-001',
            }],
        }, None, None)
        patcher2 = patch('mapit_mysociety_org.views.stripe', new=self.MockStripe)
        patcher2.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(patcher2.stop)


@override_settings(REDIS_API_NAME='test_api')
class SubscriptionTest(UserTestCase):
    def test_model(self):
        sub = Subscription.objects.create(user=self.user, stripe_id='ID')
        self.assertEqual(repr(sub), '<Subscription: Test user (ID)>')
        self.assertEqual(sub.redis_key, 'user:%d:quota:%s' % (self.user.id, 'test_api'))

    def test_redis_setting(self):
        sub = Subscription.objects.create(user=self.user, stripe_id='ID')
        sub.redis_reset_quota()
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': [], 'quota': 0, 'blocked': 0})
        r = redis_connection()
        r.set('user:%d:quota:%s:max' % (self.user.id, 'test_api'), 1000)
        r.set('user:%d:quota:%s:count' % (self.user.id, 'test_api'), 1234)
        r.set('user:%d:quota:%s:blocked' % (self.user.id, 'test_api'), 1)
        self.assertEqual(sub.redis_status(), {'count': 1234, 'history': [], 'quota': 1000, 'blocked': 1})
        sub.redis_reset_quota()
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': [b'1234'], 'quota': 1000, 'blocked': 0})
        sub.delete()
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': [b'1234'], 'quota': 0, 'blocked': 0})


class SubsFormTest(TestCase):
    def test_add_plan(self):
        data = {}
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {
            "tandcs_tick": ["Please agree to the terms and conditions"],
            "price": ["This field is required.", "You need to submit payment"]}
        )
        data.update({'tandcs_tick': True})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {"price": ["This field is required.", "You need to submit payment"]})
        data.update({'price': 'price_123'})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {"price": ["You need to submit payment"]})
        data.update({'charitable_tick': True, 'charitable': 'c'})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {'charity_number': ['Please provide your charity number']})
        data.update({'charitable': 'i'})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {'description': ['Please provide details of your project']})
        data.update({'description': 'x' * 600})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {'description': ['Ensure this value has at most 500 characters (it has 600).']})
        data.update({'description': 'My project'})
        form = SubsForm(data=data)
        self.assertTrue(form.is_valid())

    def test_update_plan(self):
        data = {'price': 'price_123'}
        form = SubsForm(stripe=True, data=data)
        self.assertEqual(form.errors, {"price": ["You need to submit payment"]})
        data.update({'stripeToken': 'TOKEN'})
        form = SubsForm(stripe=True, data=data)
        self.assertTrue(form.is_valid())

    def test_update_plan_has_payment(self):
        form = SubsForm(stripe=True, has_payment_data=True, data={'price': 'price_123'})
        self.assertTrue(form.is_valid())


class SubscriptionViewErrorTest(UserTestCase):
    @patch('subscriptions.views.stripe')
    def test_stripe_error(self, MockStripe):
        MockStripe.error.InvalidRequestError = stripe.error.InvalidRequestError
        MockStripe.Subscription.retrieve.side_effect = stripe.error.InvalidRequestError("ERROR", 'id')
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.get(reverse('subscription'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You are not currently subscribed to a plan.')
        self.assertEqual(Subscription.objects.count(), 0)


class SubscriptionViewTest(PatchedStripeMixin, UserTestCase):
    def test_view_requires_login(self):
        response = self.client.get(reverse('subscription'))
        self.assertEqual(response.status_code, 302)

    def test_subscription_page_no_plan(self):
        self.client.login(username="Test user", password="password")
        response = self.client.get(reverse('subscription'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You are not currently subscribed to a plan.')

    def test_subscription_page_with_plan(self):
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.get(reverse('subscription'))
        self.assertNotContains(response, 'You are not currently subscribed to a plan.')
        self.assertContains(response, 'Your current plan is <strong>MapIt, unlimited calls</strong>')
        self.assertContains(
            response, u'<p>It costs you £150/mth. (£300/mth with 50% discount applied.)</p>', html=True)
        self.assertRegex(response.content.decode('utf-8'), u'your next payment\\s+of £150\\s+will be taken on')
        self.assertContains(response, u'Your account has a balance of £4.')


class SubscriptionUpdateViewTest(PatchedStripeMixin, UserTestCase):
    def test_view_requires_login(self):
        response = self.client.get(reverse('subscription_update'))
        self.assertEqual(response.status_code, 302)

    def test_view_update_page_no_plan(self):
        self.client.login(username="Test user", password="password")
        response = self.client.get(reverse('subscription_update'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['price'].value(), None)
        self.assertEqual(bool(response.context['form']['charitable_tick'].value()), False)
        self.assertEqual(response.context['form']['tandcs_tick'].value(), None)
        self.assertContains(response, 'tandcs_tick')

    def test_view_update_page_with_plan(self):
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.get(reverse('subscription_update'))
        self.assertEqual(response.context['form']['price'].value(), 'price_789')
        self.assertEqual(bool(response.context['form']['charitable_tick'].value()), True)
        self.assertEqual(response.context['form']['tandcs_tick'].value(), None)
        self.assertNotContains(response, 'tandcs_tick')

    def test_update_page_no_plan(self):
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'tandcs_tick': '1',
            'price': 'price_456',
            'stripeToken': 'TOKEN',
        }, follow=True)
        self.assertRedirects(response, reverse('subscription'))
        self.MockStripe.Customer.create.assert_called_once_with(email='test@example.com', source='TOKEN')
        self.MockStripe.Subscription.create.assert_called_once_with(
            customer='CUSTOMER-ID', items=[{"price": 'price_456'}], coupon=None, default_tax_rates=[ANY],
            expand=['latest_invoice.payment_intent'], payment_behavior='allow_incomplete',
            metadata={'charitable': '', 'description': '', 'charity_number': '', 'interest_contact': 'No'})
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.stripe_id, 'SUBSCRIPTION-ID-CREATE')
        # Quota does not update until hook comes in now
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': [], 'quota': 0, 'blocked': 0})

    def test_update_page_no_plan_charitable(self):
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'tandcs_tick': '1',
            'price': 'price_123',
            'charitable_tick': '1',
            'charitable': 'c',
            'charity_number': '123',
        }, follow=True)
        self.assertRedirects(response, reverse('subscription'))
        self.MockStripe.Customer.create.assert_called_once_with(email='test@example.com')
        self.MockStripe.Subscription.create.assert_called_once_with(
            customer='CUSTOMER-ID', items=[{"price": 'price_123'}], coupon='charitable100', default_tax_rates=[ANY],
            expand=['latest_invoice.payment_intent'], payment_behavior='allow_incomplete',
            metadata={'charitable': 'c', 'description': '', 'charity_number': '123', 'interest_contact': 'No'})
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.stripe_id, 'SUBSCRIPTION-ID-CREATE')
        # Quota does not update until hook comes in now
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': [], 'quota': 0, 'blocked': 0})

    def test_update_page_with_plan_add_payment(self):
        # Set sub to 10k so this is an upgrade
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub['items'].data[0].price = convert_to_stripe_object({
            'id': 'price_123',
            'nickname': 'MapIt',
            'unit_amount': 10000
        })

        self.MockStripe.PaymentMethod.attach.return_value = convert_to_stripe_object({
            'id': 'PMPM',
        }, None, None)

        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'price': 'price_456',
            'payment_method': 'PMPM',
            'charitable_tick': 1,
            'charitable': 'c',
            'charity_number': 123,
        })
        self.assertEqual(response.status_code, 302)
        self.MockStripe.Subscription.modify.assert_called_once_with(
            'SUBSCRIPTION-ID', payment_behavior='allow_incomplete', coupon='charitable50',
            cancel_at_period_end=False,
            proration_behavior='always_invoice',
            metadata={
                'charitable': 'c', 'description': '', 'charity_number': '123', 'interest_contact': 'No'
            }, items=[{"price": 'price_456'}])

        self.client.get(response['Location'])
        self.MockStripe.PaymentMethod.attach.assert_called_once_with('PMPM', customer='CUSTOMER-ID')
        self.MockStripe.Customer.modify.assert_called_once_with(
            'CUSTOMER-ID', invoice_settings={'default_payment_method': {'id': 'PMPM'}})

    def test_update_page_with_plan_upgrade(self):
        # Set sub to 10k so this is an upgrade
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub['items'].data[0].price = convert_to_stripe_object({
            'id': 'price_123',
            'nickname': 'MapIt',
            'unit_amount': 1667,
        })

        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'price': 'price_456',
            'charitable_tick': 1,
            'charitable': 'c',
            'charity_number': 123,
        })
        self.assertEqual(response.status_code, 302)
        self.MockStripe.Customer.modify.assert_not_called()
        self.MockStripe.Subscription.modify.assert_called_once_with(
            'SUBSCRIPTION-ID', payment_behavior='allow_incomplete', coupon='charitable50',
            cancel_at_period_end=False,
            proration_behavior='always_invoice',
            metadata={
                'charitable': 'c', 'description': '', 'charity_number': '123', 'interest_contact': 'No'
            }, items=[{"price": 'price_456'}])

        # The real code refetches from stripe after the redirect
        # We need to reset the plan and the discount
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub['items'].data[0].price = convert_to_stripe_object({
            'id': 'price_456',
            'nickname': 'MapIt',
            'unit_amount': 7500
        })
        sub.discount.coupon.percent_off = 50.0
        response = self.client.get(response['Location'])
        self.assertContains(
            response, u'<p>It costs you £45/mth. (£90/mth with 50% discount applied.)</p>', html=True)

    def test_update_page_with_plan_downgrade(self):
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'price': 'price_123',
            'charitable_tick': 1,
            'charitable': 'c',
            'charity_number': 123,
        })
        self.assertEqual(response.status_code, 302)
        self.MockStripe.Customer.modify.assert_not_called()
        self.MockStripe.SubscriptionSchedule.create.assert_called_once_with(from_subscription='SUBSCRIPTION-ID')
        self.MockStripe.SubscriptionSchedule.modify.assert_called_once_with(
            'SCHEDULE-ID', phases=[{
                'items': [{'price': 'price_789'}],
                'start_date': ANY,
                'end_date': ANY,
                'default_tax_rates': [ANY],
                'proration_behavior': 'none',
                'discounts': [{'coupon': 'charitable50'}],
            }, {
                'items': [{'price': 'price_123'}],
                'iterations': 1,
                'metadata': {'charitable': 'c', 'charity_number': '123', 'description': '', 'interest_contact': 'No'},
                'default_tax_rates': [ANY],
                'proration_behavior': 'none',
                'coupon': 'charitable100'
            }
            ])

    def test_update_page_with_plan_remove_charitable_upgrade(self):
        # Set sub to 10k so this is an upgrade
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub['items'].data[0].price = convert_to_stripe_object({
            'id': 'price_123',
            'nickname': 'MapIt',
            'unit_amount': 10000
        })

        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'price': 'price_456',
        })
        self.assertEqual(response.status_code, 302)
        self.MockStripe.Customer.modify.assert_not_called()
        self.MockStripe.Subscription.modify.assert_called_once_with(
            'SUBSCRIPTION-ID', payment_behavior='allow_incomplete', coupon='',
            cancel_at_period_end=False,
            proration_behavior='always_invoice',
            metadata={
                'charitable': '', 'description': '', 'charity_number': '', 'interest_contact': 'No'
            }, items=[{"price": 'price_456'}])

        # The real code refetches from stripe after the redirect
        # We need to reset the plan and the discount
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub['items'].data[0].price = convert_to_stripe_object({
            'id': sub['items'].data[0].price.id,
            'nickname': 'MapIt',
            'unit_amount': 8333
        })
        sub.discount = None
        response = self.client.get(response['Location'])
        self.assertContains(response, u'<p>It costs you £100/mth.</p>', html=True)

    def test_update_page_with_plan_remove_charitable_downgrade(self):
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'price': 'price_456',
        })
        self.assertEqual(response.status_code, 302)
        self.MockStripe.Customer.modify.assert_not_called()

        self.MockStripe.SubscriptionSchedule.create.assert_called_once_with(from_subscription='SUBSCRIPTION-ID')
        self.MockStripe.SubscriptionSchedule.modify.assert_called_once_with(
            'SCHEDULE-ID', phases=[{
                'items': [{'price': 'price_789'}],
                'start_date': ANY,
                'end_date': ANY,
                'default_tax_rates': [ANY],
                'proration_behavior': 'none',
                'discounts': [{'coupon': 'charitable50'}],
            }, {
                'items': [{'price': 'price_456'}],
                'iterations': 1,
                'metadata': {'charitable': '', 'charity_number': '', 'description': '', 'interest_contact': 'No'},
                'default_tax_rates': [ANY],
                'proration_behavior': 'none'
            }])


class SubscriptionOtherViewsTest(PatchedStripeMixin, UserTestCase):
    def setUp(self):
        super(SubscriptionOtherViewsTest, self).setUp()
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        self.sub = self.MockStripe.Subscription.retrieve.return_value
        self.MockStripe.PaymentMethod.attach.return_value = convert_to_stripe_object({
            'id': 'PM',
        }, None, None)

    def test_invoices_page(self):
        resp = self.client.get(reverse('invoices'))
        date = '%d %s' % (int(time.strftime('%d')), time.strftime('%b %Y'))
        self.assertContains(
            resp, '<td>INVOICE-002</td><td>%s</td><td>£20</td><td>Open</td><td></td>' % date, html=True)
        self.assertContains(
            resp, '<td>INVOICE-001</td><td>%s</td><td>£20</td><td>Paid</td>'
                  '<td><a href="https://example.org/pdf-001">Download PDF</a></td>' % date, html=True)

    def test_card_update(self):
        resp = self.client.post(reverse('subscription_card_update'), data={'payment_method': 'PM'}, follow=True)
        self.assertRedirects(resp, reverse('subscription'))
        self.assertContains(resp, 'Your card details have been updated.')
        self.MockStripe.PaymentMethod.attach.assert_called_once_with('PM', customer='CUSTOMER-ID')
        self.MockStripe.Customer.modify.assert_called_once_with(
            'CUSTOMER-ID', invoice_settings={'default_payment_method': {'id': 'PM'}})

    def test_cancellation(self):
        resp = self.client.post(reverse('subscription_cancel'), follow=True)
        self.assertRedirects(resp, reverse('subscription'))
        self.assertContains(resp, 'Your subscription has been cancelled.')
        self.MockStripe.Subscription.modify.assert_called_once_with('SUBSCRIPTION-ID', cancel_at_period_end=True)


class SubscriptionHookViewTest(PatchedStripeMixin, UserTestCase):
    def setUp(self):
        super(SubscriptionHookViewTest, self).setUp()
        self.sub = Subscription.objects.create(user=self.user, stripe_id='ID')

    def post_to_hook(self, id):
        data = {'id': id}
        self.client.post(reverse('stripe-hook'), content_type='application/json', data=json.dumps(data))
        self.MockStripe.Event.retrieve.assert_called_once_with(id)

    def test_subscription_deleted(self):
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-DELETED',
            'type': 'customer.subscription.deleted',
            'data': {'object': {'id': 'ID'}}
        }, None, None)
        self.post_to_hook('EVENT-ID-DELETED')
        self.assertEqual(Subscription.objects.count(), 0)

    def test_subscription_updated(self):
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-UPDATED',
            'type': 'customer.subscription.updated',
            'data': {'object': {
                'id': 'ID',
                'items': {'data': [{
                    "price": {
                        'id': 'price_123',
                        'metadata': {'calls': 10000},
                    }
                }]}
            }}
        }, None, None)
        self.assertEqual(self.sub.redis_status(), {'count': 0, 'history': [], 'quota': 0, 'blocked': 0})
        self.post_to_hook('EVENT-ID-UPDATED')
        self.assertEqual(self.sub.redis_status(), {'count': 0, 'history': [], 'quota': 10000, 'blocked': 0})

    def test_invoice_failed_without_subscription(self):
        self.MockStripe.Subscription.retrieve.side_effect = stripe.error.InvalidRequestError(
            "Could not determine...", 'id')
        event = {
            'id': 'EVENT-INVOICE',
            'type': 'invoice.payment_failed',
            'data': {'object': {
                'id': 'INVOICE-ID',
                'customer': 'CUSTOMER-ID',
                'next_payment_attempt': 1234567890,
                'billing_reason': 'manual',
                'subscription': None
            }}
        }
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object(event, None, None)
        self.post_to_hook('EVENT-INVOICE')

    def test_invoice_failed_not_cycle(self):
        event = {
            'id': 'EVENT-ID-FAILED',
            'type': 'invoice.payment_failed',
            'data': {'object': {
                'id': 'INVOICE-ID',
                'customer': 'CUSTOMER-ID',
                'next_payment_attempt': 1234567890,
                'billing_reason': 'subscription_update',
                'subscription': 'SUBSCRIPTION-ID'
            }}
        }
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object(event, None, None)
        self.post_to_hook('EVENT-ID-FAILED')
        self.assertEqual(len(mail.outbox), 0)

    def test_invoice_failed_first_time(self):
        event = {
            'id': 'EVENT-ID-FAILED',
            'type': 'invoice.payment_failed',
            'data': {'object': {
                'id': 'INVOICE-ID',
                'customer': 'CUSTOMER-ID',
                'next_payment_attempt': 1234567890,
                'billing_reason': 'subscription_cycle',
                'subscription': 'SUBSCRIPTION-ID'
            }}
        }
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object(event, None, None)
        self.post_to_hook('EVENT-ID-FAILED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Your payment to MapIt has failed')

    def test_invoice_failed_last_time(self):
        event = {
            'id': 'EVENT-ID-FAILED',
            'type': 'invoice.payment_failed',
            'data': {'object': {
                'id': 'INVOICE-ID',
                'customer': 'CUSTOMER-ID',
                'next_payment_attempt': None,
                'billing_reason': 'subscription_cycle',
                'subscription': 'SUBSCRIPTION-ID'
            }}
        }
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object(event, None, None)
        self.post_to_hook('EVENT-ID-FAILED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Your subscription to MapIt has been cancelled')

    @override_settings(REDIS_API_NAME='test_api')
    def test_invoice_updated_not_forgiven(self):
        r = redis_connection()
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-FORGIVEN',
            'type': 'invoice.updated',
            'data': {'object': {
                'id': 'INVOICE-ID', 'subscription': 'ID', 'status': 'open', 'billing_reason': 'manual'
            }}
        }, None, None)
        r.set('user:%d:quota:%s:count' % (self.user.id, 'test_api'), 1234)
        self.assertEqual(self.sub.redis_status(), {'count': 1234, 'history': [], 'quota': 0, 'blocked': 0})
        self.post_to_hook('EVENT-ID-FORGIVEN')
        self.assertEqual(self.sub.redis_status(), {'count': 1234, 'history': [], 'quota': 0, 'blocked': 0})

    @override_settings(REDIS_API_NAME='test_api')
    def test_invoice_updated_forgiven(self):
        r = redis_connection()
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-FORGIVEN',
            'type': 'invoice.updated',
            'data': {
                'object': {'id': 'INVOICE-ID', 'subscription': 'ID',
                           'status': 'uncollectible', 'billing_reason': 'manual'},
                'previous_attributes': {'status': 'open'}
            }
        }, None, None)
        r.set('user:%d:quota:%s:count' % (self.user.id, 'test_api'), 1234)
        self.assertEqual(self.sub.redis_status(), {'count': 1234, 'history': [], 'quota': 0, 'blocked': 0})
        self.post_to_hook('EVENT-ID-FORGIVEN')
        self.assertEqual(self.sub.redis_status(), {'count': 0, 'history': [b'1234'], 'quota': 0, 'blocked': 0})

    def test_invoice_succeeded_no_sub_here(self):
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-SUCCEEDED',
            'type': 'invoice.payment_succeeded',
            'data': {'object': {
                'id': 'INVOICE-ID', 'subscription': 'SUBSCRIPTION-ID', 'charge': 'CHARGE',
                'billing_reason': 'subscription_cycle', 'payment_intent': 'PI',
            }}
        }, None, None)
        self.post_to_hook('EVENT-ID-SUCCEEDED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Someone's subscription was not renewed properly")

    @override_settings(REDIS_API_NAME='test_api')
    def test_manual_invoice_succeeded_sub_present(self):
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-SUCCEEDED',
            'type': 'invoice.payment_succeeded',
            'data': {'object': {
                'id': 'INVOICE-ID', 'subscription': 'ID', 'charge': 'CHARGE',
                'billing_reason': 'manual', 'payment_intent': 'PI',
            }}
        }, None, None)
        r = redis_connection()
        r.set('user:%d:quota:%s:count' % (self.user.id, 'test_api'), 1234)
        r.set('user:%d:quota:%s:max' % (self.user.id, 'test_api'), 100000)
        self.assertEqual(self.sub.redis_status(), {'count': 1234, 'history': [], 'quota': 100000, 'blocked': 0})
        self.post_to_hook('EVENT-ID-SUCCEEDED')
        # Quota does not reset for manual invoices
        self.assertEqual(self.sub.redis_status(), {'count': 1234, 'history': [], 'quota': 0, 'blocked': 0})
        self.MockStripe.Charge.modify.assert_called_once_with('CHARGE', description='MapIt')
        self.MockStripe.PaymentIntent.modify.assert_called_once_with('PI', description='MapIt')

    @override_settings(REDIS_API_NAME='test_api')
    def test_invoice_succeeded_sub_present(self):
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-SUCCEEDED',
            'type': 'invoice.payment_succeeded',
            'data': {'object': {
                'id': 'INVOICE-ID', 'subscription': 'ID', 'charge': 'CHARGE',
                'billing_reason': 'subscription_cycle', 'payment_intent': 'PI',
            }}
        }, None, None)
        r = redis_connection()
        r.set('user:%d:quota:%s:count' % (self.user.id, 'test_api'), 1234)
        r.set('user:%d:quota:%s:max' % (self.user.id, 'test_api'), 100000)
        self.assertEqual(self.sub.redis_status(), {'count': 1234, 'history': [], 'quota': 100000, 'blocked': 0})
        self.post_to_hook('EVENT-ID-SUCCEEDED')
        self.assertEqual(self.sub.redis_status(), {'count': 0, 'history': [b'1234'], 'quota': 0, 'blocked': 0})
        self.MockStripe.Charge.modify.assert_called_once_with('CHARGE', description='MapIt')
        self.MockStripe.PaymentIntent.modify.assert_called_once_with('PI', description='MapIt')


class PriceChangeTest(PatchedStripeMixin, UserTestCase):
    def setUp(self):
        super().setUp()
        Subscription.objects.create(user=self.user, stripe_id='ID')
        self.MockStripe.Price.list.return_value = convert_to_stripe_object({
            'data': [
                {'id': 'price_789',
                 'metadata': {'calls': '0'},
                 'product': {'id': 'prod_GHI', 'name': 'MapIt, unlimited calls'}},
                {'id': 'price_789b',
                 'metadata': {'calls': '0'},
                 'product': {'id': 'prod_GHI', 'name': 'MapIt, unlimited calls'}},
                {'id': 'price_123',
                 'metadata': {'calls': '10000'},
                 'product': {'id': 'prod_ABC', 'name': 'MapIt, 10,000 calls'}},
                {'id': 'price_123b',
                 'metadata': {'calls': '10000'},
                 'product': {'id': 'prod_ABC', 'name': 'MapIt, 10,000 calls'}},
                {'id': 'price_456',
                 'metadata': {'calls': '100000'},
                 'product': {'id': 'prod_DEF', 'name': 'MapIt, 100,000 calls'}},
                {'id': 'price_456b',
                 'metadata': {'calls': '100000'},
                 'product': {'id': 'prod_DEF', 'name': 'MapIt, 100,000 calls'}},
            ]
        }, None, None)

    def test_change_price_charitable_sub(self):
        with patch('subscriptions.management.commands.schedule_price_change.stripe', self.MockStripe):
            call_command(
                'schedule_price_change', '--old', 'price_789', '--new', 'price_789b',
                '--commit', stdout=StringIO(), stderr=StringIO())

        self.MockStripe.SubscriptionSchedule.create.assert_called_once_with(
            from_subscription='SUBSCRIPTION-ID')
        self.MockStripe.SubscriptionSchedule.modify.assert_called_once_with(
            'SCHEDULE-ID', phases=[{
                'items': [{'price': 'price_789'}],
                'start_date': ANY,
                'iterations': 2,
                'proration_behavior': 'none',
                'default_tax_rates': [ANY],
                'discounts': [{'coupon': 'charitable50'}]
            }, {
                'items': [{'price': 'price_789b'}],
                'iterations': 1,
                'proration_behavior': 'none',
                'default_tax_rates': [ANY],
                'discounts': [{'coupon': 'charitable50'}]
            }])

    def test_change_price_non_charitable_sub(self):
        sub = self.MockStripe.SubscriptionSchedule.create.return_value
        sub.phases[0].discounts = None
        with patch('subscriptions.management.commands.schedule_price_change.stripe', self.MockStripe):
            call_command(
                'schedule_price_change', '--old', 'price_789', '--new', 'price_789b',
                '--commit', stdout=StringIO(), stderr=StringIO())

        self.MockStripe.SubscriptionSchedule.create.assert_called_once_with(
            from_subscription='SUBSCRIPTION-ID')
        self.MockStripe.SubscriptionSchedule.modify.assert_called_once_with(
            'SCHEDULE-ID', phases=[{
                'items': [{'price': 'price_789'}],
                'start_date': ANY,
                'iterations': 2,
                'proration_behavior': 'none',
                'default_tax_rates': [ANY],
            }, {
                'items': [{'price': 'price_789b'}],
                'iterations': 1,
                'proration_behavior': 'none',
                'default_tax_rates': [ANY],
            }])

    def test_change_price_just_downgraded(self):
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub.schedule = convert_to_stripe_object({
            'id': 'SCHEDULE-ID',
            'phases': [{
                'start_date': time.time(),
                'end_date': time.time(),
                'discounts': [{'coupon': 'charitable50'}],
                'items': [{
                    'price': 'price_789',
                }]
            }, {
                'start_date': time.time(),
                'end_date': time.time(),
                'discounts': [{'coupon': 'charitable50'}],
                'items': [{
                    'price': 'price_456',
                }]
            }],
        }, None, None)
        with patch('subscriptions.management.commands.schedule_price_change.stripe', self.MockStripe):
            call_command(
                'schedule_price_change', '--old', 'price_456', '--new', 'price_456b',
                '--commit', stdout=StringIO(), stderr=StringIO())

        self.MockStripe.SubscriptionSchedule.modify.assert_called_once_with(
            'SCHEDULE-ID', phases=[{
                'items': [{'price': 'price_789'}],
                'start_date': ANY,
                'end_date': ANY,
                'discounts': [{'coupon': 'charitable50'}]
            }, {
                'items': [{'price': 'price_456'}],
                'start_date': ANY,
                'end_date': ANY,
                'discounts': [{'coupon': 'charitable50'}]
            }, {
                'items': [{'price': 'price_456b'}],
                'iterations': 1,
                'proration_behavior': 'none',
                'default_tax_rates': [ANY],
                'discounts': [{'coupon': 'charitable50'}]
            }])

    def test_change_price_downgraded_last_month(self):
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub.schedule = convert_to_stripe_object({
            'id': 'SCHEDULE-ID',
            'phases': [{
                'start_date': time.time(),
                'end_date': time.time(),
                'discounts': [{'coupon': 'charitable50'}],
                'items': [{
                    'price': 'price_456',
                }]
            }],
        }, None, None)
        sub = self.MockStripe.SubscriptionSchedule.create.return_value
        sub.phases[0].discounts = None
        sub.phases[0]['items'][0].price = 'price_456'
        with patch('subscriptions.management.commands.schedule_price_change.stripe', self.MockStripe):
            call_command(
                'schedule_price_change', '--old', 'price_456', '--new', 'price_456b',
                '--commit', stdout=StringIO(), stderr=StringIO())

        self.MockStripe.SubscriptionSchedule.create.assert_called_once_with(
            from_subscription='SUBSCRIPTION-ID')
        self.MockStripe.SubscriptionSchedule.modify.assert_called_once_with(
            'SCHEDULE-ID', phases=[{
                'items': [{'price': 'price_456'}],
                'iterations': 2,
                'start_date': ANY,
                'proration_behavior': 'none',
                'default_tax_rates': [ANY],
            }, {
                'items': [{'price': 'price_456b'}],
                'iterations': 1,
                'proration_behavior': 'none',
                'default_tax_rates': [ANY],
            }])


@override_settings(REDIS_API_NAME='test_api')
class ManagementTest(PatchedRedisTestCase):
    @override_settings(API_THROTTLE_UNLIMITED=['127.0.0.4'])
    def test_default_quota(self):
        call_command('subscription_default_quota', stdout=StringIO(), stderr=StringIO())
        call_command('subscription_default_quota', verbosity=2, stdout=StringIO(), stderr=StringIO())

    def _test_reset_ip_quotas(self, **kwargs):
        r = redis_connection()
        r.set('user:127.0.0.2:quota:test_api:count', 42)
        r.set('user:127.0.0.3:quota:test_api:blocked', 1)
        r.set('user:fc00:1::1:quota:test_api:count', 57)
        r.set('user:fc00:1::1:quota:test_api:blocked', 1)

        self.assertEqual(r.get('user:127.0.0.2:quota:test_api:count'), b'42')
        self.assertEqual(r.get('user:127.0.0.3:quota:test_api:blocked'), b'1')
        self.assertEqual(r.get('user:fc00:1::1:quota:test_api:count'), b'57')
        self.assertEqual(r.get('user:fc00:1::1:quota:test_api:blocked'), b'1')

        call_command('reset_ip_quotas', stdout=StringIO(), stderr=StringIO(), **kwargs)

        self.assertIsNone(r.get('user:127.0.0.2:quota:test_api:count'))
        self.assertIsNone(r.get('user:127.0.0.3:quota:test_api:blocked'))
        self.assertIsNone(r.get('user:fc00:1::1:quota:test_api:count'))
        self.assertIsNone(r.get('user:fc00:1::1:quota:test_api:blocked'))

    def test_reset_ip_quotas(self):
        self._test_reset_ip_quotas()
        self._test_reset_ip_quotas(verbosity=2)
