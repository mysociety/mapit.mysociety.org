# encoding: utf-8

import json
from StringIO import StringIO
import time
from mock import patch, Mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test.utils import override_settings
import stripe
from stripe.resource import convert_to_stripe_object

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
            'start': time.time(),
            'current_period_start': time.time(),
            'current_period_end': time.time(),
            'cancel_at_period_end': False,
            'discount': {
                'coupon': {
                    'percent_off': 50,
                },
                'end': time.time(),
            },
            'metadata': {
                'charitable': 'c',
                'charity_number': 123,
            },
            'customer': Mock(spec_set=['default_source', 'source', 'save']),
            'plan': {
                'id': 'mapit-0k',
                'name': 'MapIt, unlimited calls',
                'amount': 30000,
            },
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
        self.addCleanup(patcher.stop)


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
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': ['1234'], 'quota': 1000, 'blocked': 0})
        sub.delete()
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': ['1234'], 'quota': 0, 'blocked': 0})


class SubsFormTest(TestCase):
    def test_add_plan(self):
        data = {}
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {
            "tandcs_tick": ["Please agree to the terms and conditions"],
            "plan": ["This field is required.", "You need to submit payment"]}
        )
        data.update({'tandcs_tick': True})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {"plan": ["This field is required.", "You need to submit payment"]})
        data.update({'plan': 'mapit-10k'})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {"plan": ["You need to submit payment"]})
        data.update({'charitable_tick': True, 'charitable': 'c'})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {'charity_number': ['Please provide your charity number']})
        data.update({'charitable': 'i'})
        form = SubsForm(data=data)
        self.assertEqual(form.errors, {'description': ['Please provide details of your project']})
        data.update({'description': 'My project'})
        form = SubsForm(data=data)
        self.assertTrue(form.is_valid())

    def test_update_plan(self):
        data = {'plan': 'mapit-10k'}
        form = SubsForm(stripe=True, data=data)
        self.assertEqual(form.errors, {"plan": ["You need to submit payment"]})
        data.update({'stripeToken': 'TOKEN'})
        form = SubsForm(stripe=True, data=data)
        self.assertTrue(form.is_valid())

    def test_update_plan_has_payment(self):
        form = SubsForm(stripe=True, has_payment_data=True, data={'plan': 'mapit-0k'})
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


class SubscriptionUpdateViewTest(PatchedStripeMixin, UserTestCase):
    def test_view_requires_login(self):
        response = self.client.get(reverse('subscription_update'))
        self.assertEqual(response.status_code, 302)

    def test_view_update_page_no_plan(self):
        self.client.login(username="Test user", password="password")
        response = self.client.get(reverse('subscription_update'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['plan'].value(), None)
        self.assertEqual(bool(response.context['form']['charitable_tick'].value()), False)
        self.assertEqual(response.context['form']['tandcs_tick'].value(), None)
        self.assertContains(response, 'tandcs_tick')

    def test_view_update_page_with_plan(self):
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.get(reverse('subscription_update'))
        self.assertEqual(response.context['form']['plan'].value(), 'mapit-0k')
        self.assertEqual(bool(response.context['form']['charitable_tick'].value()), True)
        self.assertEqual(response.context['form']['tandcs_tick'].value(), None)
        self.assertNotContains(response, 'tandcs_tick')

    def test_update_page_no_plan(self):
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'tandcs_tick': '1',
            'plan': 'mapit-100k',
            'stripeToken': 'TOKEN',
        }, follow=True)
        self.assertRedirects(response, reverse('subscription'))
        self.MockStripe.Customer.create.assert_called_once_with(email='test@example.com', source='TOKEN')
        self.MockStripe.Subscription.create.assert_called_once_with(
            customer='CUSTOMER-ID', plan='mapit-100k', coupon=None,
            metadata={'charitable': '', 'description': '', 'charity_number': ''})
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.stripe_id, 'SUBSCRIPTION-ID-CREATE')
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': [], 'quota': 100000, 'blocked': 0})

    def test_update_page_no_plan_charitable(self):
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'tandcs_tick': '1',
            'plan': 'mapit-10k',
            'charitable_tick': '1',
            'charitable': 'c',
            'charity_number': '123',
        }, follow=True)
        self.assertRedirects(response, reverse('subscription'))
        self.MockStripe.Customer.create.assert_called_once_with(email='test@example.com')
        self.MockStripe.Subscription.create.assert_called_once_with(
            customer='CUSTOMER-ID', plan='mapit-10k', coupon='charitable100',
            metadata={'charitable': 'c', 'description': '', 'charity_number': '123'})
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.stripe_id, 'SUBSCRIPTION-ID-CREATE')
        self.assertEqual(sub.redis_status(), {'count': 0, 'history': [], 'quota': 10000, 'blocked': 0})

    def test_update_page_with_plan_add_payment(self):
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub.save = Mock()

        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'plan': 'mapit-100k',
            'stripeToken': 'TOKEN',
            'charitable_tick': 1,
            'charitable': 'c',
            'charity_number': 123,
        })
        self.assertEqual(response.status_code, 302)
        # The real code refetches from stripe after the redirect
        # Our test, the plan is no longer a dict so we need to make it so
        self.assertEqual(sub.plan, 'mapit-100k')
        sub.plan = {'id': sub.plan, 'name': 'MapIt', 'amount': 10000}
        self.client.get(response['Location'])

        self.assertEqual(sub.customer.source, 'TOKEN')
        sub.customer.save.assert_called_once_with()
        sub.save.assert_called_once_with()

    def test_update_page_with_plan(self):
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub.save = Mock()

        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'plan': 'mapit-10k',
            'charitable_tick': 1,
            'charitable': 'c',
            'charity_number': 123,
        })
        self.assertEqual(response.status_code, 302)
        sub.customer.save.assert_not_called()
        sub.save.assert_called_once_with()
        self.assertEqual(sub.plan, 'mapit-10k')
        self.assertEqual(sub.coupon, 'charitable100')
        # The real code refetches from stripe after the redirect
        # We need to reset the plan and the discount
        sub.plan = {'id': sub.plan, 'name': 'MapIt', 'amount': 2000}
        sub.discount.coupon.percent_off = 100
        response = self.client.get(response['Location'])
        self.assertContains(
            response, u'<p>It costs you £0/mth. (£20/mth with 100% discount applied.)</p>', html=True)

    def test_update_page_with_plan_remove_charitable(self):
        sub = self.MockStripe.Subscription.retrieve.return_value
        sub.save = Mock()
        sub.delete_discount = Mock()

        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        response = self.client.post(reverse('subscription_update'), {
            'plan': 'mapit-100k',
        })
        self.assertEqual(response.status_code, 302)
        sub.customer.save.assert_not_called()
        sub.delete_discount.assert_called_once_with()
        sub.save.assert_called_once_with()
        self.assertEqual(sub.plan, 'mapit-100k')
        # The real code refetches from stripe after the redirect
        # We need to reset the plan and the discount
        sub.plan = {'id': sub.plan, 'name': 'MapIt', 'amount': 10000}
        sub.discount = None
        response = self.client.get(response['Location'])
        self.assertContains(response, u'<p>It costs you £100/mth.</p>', html=True)


class SubscriptionOtherViewsTest(PatchedStripeMixin, UserTestCase):
    def setUp(self):
        super(SubscriptionOtherViewsTest, self).setUp()
        Subscription.objects.create(user=self.user, stripe_id='SUBSCRIPTION-ID')
        self.client.login(username="Test user", password="password")
        self.sub = self.MockStripe.Subscription.retrieve.return_value

    def test_card_update(self):
        resp = self.client.post(reverse('subscription_card_update'), data={'stripeToken': 'TOKEN'}, follow=True)
        self.assertRedirects(resp, reverse('subscription'))
        self.assertContains(resp, 'Your card details have been updated.')
        self.assertEqual(self.sub.customer.source, 'TOKEN')
        self.sub.customer.save.assert_called_once_with()

    def test_cancellation(self):
        self.sub.delete = Mock()
        resp = self.client.post(reverse('subscription_cancel'), follow=True)
        self.assertRedirects(resp, reverse('subscription'))
        self.assertContains(resp, 'Your subscription has been cancelled.')
        self.sub.delete.assert_called_once_with(at_period_end=True)


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
            'data': {'object': {'id': 'ID', 'plan': {'id': 'mapit-10k'}}}
        }, None, None)
        self.assertEqual(self.sub.redis_status(), {'count': 0, 'history': [], 'quota': 0, 'blocked': 0})
        self.post_to_hook('EVENT-ID-UPDATED')
        self.assertEqual(self.sub.redis_status(), {'count': 0, 'history': [], 'quota': 10000, 'blocked': 0})

    def test_invoice_failed_first_time(self):
        event = {
            'id': 'EVENT-ID-FAILED',
            'type': 'invoice.payment_failed',
            'data': {'object': {'id': 'INVOICE-ID', 'customer': 'CUSTOMER-ID', 'next_payment_attempt': 1234567890}}
        }
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object(event, None, None)
        self.post_to_hook('EVENT-ID-FAILED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Your payment to MapIt has failed')

    def test_invoice_failed_last_time(self):
        event = {
            'id': 'EVENT-ID-FAILED',
            'type': 'invoice.payment_failed',
            'data': {'object': {'id': 'INVOICE-ID', 'customer': 'CUSTOMER-ID', 'next_payment_attempt': None}}
        }
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object(event, None, None)
        self.post_to_hook('EVENT-ID-FAILED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Your subscription to MapIt has been cancelled')

    def test_invoice_succeeded_no_sub_here(self):
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-SUCCEEDED',
            'type': 'invoice.payment_succeeded',
            'data': {'object': {'id': 'INVOICE-ID', 'subscription': 'SUBSCRIPTION-ID'}}
        }, None, None)
        self.post_to_hook('EVENT-ID-SUCCEEDED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Someone's subscription was not renewed properly")

    @override_settings(REDIS_API_NAME='test_api')
    def test_invoice_succeeded_sub_present(self):
        self.MockStripe.Event.retrieve.return_value = convert_to_stripe_object({
            'id': 'EVENT-ID-SUCCEEDED',
            'type': 'invoice.payment_succeeded',
            'data': {'object': {'id': 'INVOICE-ID', 'subscription': 'ID'}}
        }, None, None)
        r = redis_connection()
        r.set('user:%d:quota:%s:count' % (self.user.id, 'test_api'), 1234)
        self.assertEqual(self.sub.redis_status(), {'count': 1234, 'history': [], 'quota': 0, 'blocked': 0})
        self.post_to_hook('EVENT-ID-SUCCEEDED')
        self.assertEqual(self.sub.redis_status(), {'count': 0, 'history': ['1234'], 'quota': 0, 'blocked': 0})


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
        call_command('reset_ip_quotas', stdout=StringIO(), stderr=StringIO(), **kwargs)

    def test_reset_ip_quotas(self):
        self._test_reset_ip_quotas()
        self._test_reset_ip_quotas(verbosity=2)
