from StringIO import StringIO

from mock import patch
from mockredis import mock_strict_redis_client

from django.test import TestCase
from django.test.utils import override_settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core.management import call_command

from account.signals import user_signed_up

from .models import APIKey, create_key_for_new_user
from .utils import redis_connection, RedisStrings


class PatchedRedisTestCase(TestCase):
    """
    Helper TestCase subclass that patches the redis library.
    """

    def setUp(self):
        self.redis_patcher = patch('api_keys.utils.redis.StrictRedis', mock_strict_redis_client)
        self.redis_patcher.start()

    def tearDown(self):
        self.redis_patcher.stop()


class SignalsTest(PatchedRedisTestCase):

    def setUp(self):
        super(SignalsTest, self).setUp()
        self.user = User.objects.create_user("Test user", "test@example.com", "password")

    def tearDown(self):
        super(SignalsTest, self).tearDown()
        self.user.delete()

    def test_creates_key_when_user_signs_up(self):
        self.assertFalse(APIKey.objects.filter(user=self.user).exists())
        user_signed_up.send(self.__class__, user=self.user, form={})
        self.assertTrue(APIKey.objects.filter(user=self.user).exists())
        APIKey.objects.get(user=self.user).delete()

    def test_deletes_existing_key(self):
        key = APIKey.objects.create(user=self.user, key=APIKey.generate_key())
        create_key_for_new_user(self.user, form={})
        self.assertNotEqual(key, APIKey.objects.get(user=self.user))
        key.delete()


class APIKeyDetailViewTest(PatchedRedisTestCase):

    def setUp(self):
        super(APIKeyDetailViewTest, self).setUp()
        self.user = User.objects.create_user("Test user", "test@example.com", "password")
        self.key = APIKey.objects.create(user=self.user, key=APIKey.generate_key())

    def tearDown(self):
        super(APIKeyDetailViewTest, self).tearDown()
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


class APIKeyModelTest(PatchedRedisTestCase):

    def setUp(self):
        super(APIKeyModelTest, self).setUp()
        self.user = User.objects.create_user("Test user", "test@example.com", "password")

    def tearDown(self):
        super(APIKeyModelTest, self).tearDown()
        # Some tests already delete the user
        if self.user.id:
            self.user.delete()

    @override_settings(REDIS_API_NAME='test_api')
    def test_redis_api_key(self):
        key = APIKey.objects.create(user=self.user, key="test_key")
        self.assertEqual("key:test_key:api:test_api", key.redis_key)
        key.delete()

    @override_settings(REDIS_API_NAME='test_api')
    def test_sets_key_in_redis(self):
        expected_key = "key:test_key:api:test_api"
        r = redis_connection()
        self.assertIsNone(r.get(expected_key))
        key = APIKey.objects.create(user=self.user, key="test_key")
        self.assertEqual(r.get(expected_key), '1')
        key.delete()

    @override_settings(REDIS_API_NAME='test_api')
    def test_deletes_key_from_redis(self):
        expected_key = "key:test_key:api:test_api"
        r = redis_connection()
        key = APIKey.objects.create(user=self.user, key="test_key")
        self.assertEqual(r.get(expected_key), '1')
        key.delete()
        self.assertIsNone(r.get(expected_key))

    @override_settings(REDIS_API_NAME='test_api')
    def test_deleted_users_cascade(self):
        expected_key = "key:test_key:api:test_api"
        key = APIKey.objects.create(user=self.user, key="test_key")
        r = redis_connection()
        self.assertEqual(r.get(expected_key), '1')
        self.user.delete()
        with self.assertRaises(APIKey.DoesNotExist):
            APIKey.objects.get(pk=key.pk)
        self.assertIsNone(r.get(expected_key))


class RestrictAPICommandTest(PatchedRedisTestCase):

    @override_settings(REDIS_API_NAME='test_api', API_RESTRICT=True)
    def test_restricts_api(self):
        r = redis_connection()
        self.assertIsNone(r.get(RedisStrings.API_RESTRICT))
        call_command('api_keys_restrict_api', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(r.get(RedisStrings.API_RESTRICT), '1')

    @override_settings(REDIS_API_NAME='test_api', API_RESTRICT=False)
    def test_unrestricts_api(self):
        r = redis_connection()
        r.set(RedisStrings.API_RESTRICT, '1')
        self.assertEqual(r.get(RedisStrings.API_RESTRICT), '1')
        call_command('api_keys_restrict_api', stdout=StringIO(), stderr=StringIO())
        self.assertIsNone(r.get(RedisStrings.API_RESTRICT))
