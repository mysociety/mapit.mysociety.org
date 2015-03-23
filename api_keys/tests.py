from django.test import TestCase
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from account.signals import user_signed_up

from .models import APIKey, create_key_for_new_user


class SignalsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("Test user", "test@example.com", "password")

    def tearDown(self):
        self.user.delete()

    def test_creates_key_when_user_signs_up(self):
        self.assertFalse(APIKey.objects.filter(user=self.user).exists())
        user_signed_up.send(self.__class__, user=self.user, form={})
        self.assertTrue(APIKey.objects.filter(user=self.user).exists())

    def test_deletes_existing_key(self):
        key = APIKey.objects.create(user=self.user, key=APIKey.generate_key())
        create_key_for_new_user(self.user, form={})
        self.assertNotEqual(key, APIKey.objects.get(user=self.user))


class APIKeyDetailViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("Test user", "test@example.com", "password")
        self.key = APIKey.objects.create(user=self.user, key=APIKey.generate_key())

    def tearDown(self):
        self.user.delete()
        self.key.delete()

    def test_view_requires_login(self):
        url = reverse('api_keys_key')
        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.client.login(username="Test user", password="password")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


    def test_prints_api_key(self):
        url = reverse('api_keys_key')
        self.client.login(username="Test user", password="password")
        response = self.client.get(url)
        self.assertContains(response, self.key.key)
