# encoding: utf-8

import re
from io import StringIO
from mock import patch

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.test.utils import override_settings
from stripe import convert_to_stripe_object
import stripe

from subscriptions.models import Subscription
from subscriptions.tests import PatchedStripeMixin
from api_keys.tests import PatchedRedisTestCase


class SignupViewTest(PatchedStripeMixin, PatchedRedisTestCase):
    @patch('socket.getfqdn')
    def test_signup(self, socket):
        socket.return_value = 'example.net'
        self.client.get(reverse('account_signup'))
        resp = self.client.post(reverse('account_signup'), {
            'email': 'testing@example.net',
            'password': 'password',
            'password_confirm': 'password',
            'tandcs_tick': 1,
            'price': 'price_123',
            'charitable_tick': 1,
            'charitable': 'c',
            'charity_number': '123',
        }, follow=True)
        self.assertRedirects(resp, reverse('subscription'))
        # The test Stripe response will be unlimited with charity discount
        self.assertContains(resp, 'Your current plan is <strong>MapIt, unlimited calls</strong>')
        self.assertContains(
            resp, u'<p>It costs you £150/mth. (£300/mth with 50% discount applied.)</p>', html=True)
        self.assertEqual(len(mail.outbox), 1)

        m = re.search(r'https:[^\s]*', mail.outbox[0].body)
        link = m.group()
        self.client.get(link)
        self.MockStripe.Customer.modify.assert_called_once_with(
            'CUSTOMER-ID', email='testing@example.net')

        self.client.get(reverse('account_logout'))

    def test_signup_card_error(self):
        self.MockStripe.error.CardError = stripe.error.CardError
        self.MockStripe.error.InvalidRequestError = stripe.error.InvalidRequestError
        self.MockStripe.Customer.create.side_effect = stripe.error.CardError(
            'Your postcode did not match', 'PARAM', '400')
        self.client.get(reverse('account_signup'))
        resp = self.client.post(reverse('account_signup'), {
            'email': 'testing@example.net',
            'password': 'password',
            'password_confirm': 'password',
            'tandcs_tick': 1,
            'price': 'price_123',
            'charitable_tick': 1,
            'charitable': 'c',
            'charity_number': '123',
        })
        self.assertContains(resp, 'Your postcode did not match')


@override_settings(REDIS_API_NAME='test_api')
class ManagementTest(PatchedStripeMixin, PatchedRedisTestCase):
    def test_add_mapit_user(self):
        with patch('mapit_mysociety_org.management.commands.add_mapit_user.stripe', self.MockStripe):
            self.MockStripe.Price.list.return_value = convert_to_stripe_object({
                'data': [
                    {'id': 'price_789',
                     'metadata': {'calls': '0'},
                     'product': {'id': 'prod_GHI', 'name': 'MapIt, unlimited calls'}},
                    {'id': 'price_123',
                     'metadata': {'calls': '10000'},
                     'product': {'id': 'prod_ABC', 'name': 'MapIt, 10,000 calls'}},
                    {'id': 'price_456',
                     'metadata': {'calls': '100000'},
                     'product': {'id': 'prod_DEF', 'name': 'MapIt, 100,000 calls'}},
                ]
            }, None, None)
            call_command(
                'add_mapit_user', '--email', 'test@example.com', '--price', "MapIt, 100,000 calls",
                coupon='charitable25-6months', trial='10',
                stdout=StringIO(), stderr=StringIO())

        self.MockStripe.Coupon.create.assert_called_once_with(
            id='charitable25-6months', duration='repeating', duration_in_months='6', percent_off='25')
        self.MockStripe.Subscription.create.assert_called_once_with(
            customer='CUSTOMER-ID', items=[{"price": 'price_456'}],
            coupon='charitable25-6months', trial_period_days='10')

        user = User.objects.get(email='test@example.com')
        sub = Subscription.objects.get(user=user)
        self.assertEqual(sub.stripe_id, 'SUBSCRIPTION-ID-CREATE')

    def test_create_default_site(self):
        call_command('create_default_site', verbosity=2, stdout=StringIO(), stderr=StringIO())

    def test_create_default_site_first_time(self):
        Site.objects.all().delete()
        call_command('create_default_site', stdout=StringIO(), stderr=StringIO())
