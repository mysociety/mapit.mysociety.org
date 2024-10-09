import os
import sys
import yaml

# Import MapIt's settings (first time to quiet flake8)
from .mapit_settings import (
    config, INSTALLED_APPS, TEMPLATES, MIDDLEWARE, STATICFILES_DIRS, BASE_DIR, MAPIT_RATE_LIMIT, PARENT_DIR, DATABASES)
from .mapit_settings import *  # noqa

# Update a couple of things to suit our changes

if config.get('MAPIT_DB_RO_HOST', '') and 'test' not in sys.argv:
    DATABASES['replica'] = {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': config.get('MAPIT_DB_NAME', 'mapit'),
        'USER': config.get('MAPIT_DB_USER', 'mapit'),
        'PASSWORD': config.get('MAPIT_DB_PASS', ''),
        'HOST': config['MAPIT_DB_RO_HOST'],
        'PORT': config['MAPIT_DB_RO_PORT'],
        # Should work, but does not appear to (hence sys.argv test above); see
        # https://stackoverflow.com/questions/33941139/test-mirror-default-database-but-no-data
        # 'TEST': {
        #     'MIRROR': 'default',
        # },
    }

    import random
    from .multidb import use_primary

    class PrimaryReplicaRouter(object):
        """A basic primary/replica database router."""
        def db_for_read(self, model, **hints):
            """Randomly pick between default and replica databases, unless the
            request (via middleware) demands we use the primary."""
            if use_primary():
                return 'default'
            return random.choice(['default', 'replica'])

        def db_for_write(self, model, **hints):
            """Always write to the primary database."""
            return 'default'

        def allow_relation(self, obj1, obj2, **hints):
            """Any relation between objects is allowed, as same data."""
            return True

        def allow_migrate(self, db, app_label, model_name=None, **hints):
            """migrate is only ever called on the default database."""
            return True

    DATABASE_ROUTERS = ['mapit_mysociety_org.settings.PrimaryReplicaRouter']
    MIDDLEWARE.insert(0, 'mapit_mysociety_org.middleware.force_primary_middleware')

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

INSTALLED_APPS.extend(['django.contrib.sites', 'account', 'mailer', 'api_keys', 'subscriptions', 'bulk_lookup'])

# Insert our project app before mapit and mapit_gb so that the templates
# take precedence
INSTALLED_APPS.insert(INSTALLED_APPS.index('mapit_gb'), 'mapit_mysociety_org')
ROOT_URLCONF = 'mapit_mysociety_org.urls'
WSGI_APPLICATION = 'mapit_mysociety_org.wsgi.application'

old_context_processors = TEMPLATES[0]['OPTIONS']['context_processors']
TEMPLATES[0]['OPTIONS']['context_processors'] = old_context_processors + (
    'account.context_processors.account',
    'mapit_mysociety_org.context_processors.add_settings',
)

MIDDLEWARE.extend([
    'mapit_mysociety_org.middleware.add_api_key',
    'django.middleware.csrf.CsrfViewMiddleware',
    "account.middleware.LocaleMiddleware",
    "account.middleware.TimezoneMiddleware",
])

APPEND_SLASH = False

old_staticfiles_dirs = STATICFILES_DIRS
STATICFILES_DIRS = old_staticfiles_dirs + (
    os.path.join(BASE_DIR, 'static'),
)

MEDIA_ROOT = os.path.join(PARENT_DIR, 'uploaded_files')
MEDIA_URL = '/uploads/'

# New mapit.mysociety.org settings

if 'test' in sys.argv:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Config for Django's sites framework, needed so that we can send emails from
# django-user-accounts with fully qualifed urls in
SITE_ID = 1
SITE_BASE_URL = config.get('SITE_BASE_URL', '')
SITE_NAME = config.get('SITE_NAME', 'MapIt')

LOGIN_URL = '/account/login/'

# django-user-accounts settings
# Emails must be unique because we use them as usernames
ACCOUNT_EMAIL_UNIQUE = True
CONTACT_EMAIL = config.get('CONTACT_EMAIL', '')
DEFAULT_FROM_EMAIL = CONTACT_EMAIL
ACCOUNT_USER_DISPLAY = lambda user: user.email  # noqa
ACCOUNT_LOGOUT_REDIRECT_URL = 'mapit_index'
ACCOUNT_SIGNUP_REDIRECT_URL = '/account/subscription'
ACCOUNT_LOGIN_REDIRECT_URL = '/account/subscription'
DEFAULT_HTTP_PROTOCOL = 'https'
# Enable authentication by email address not username
AUTHENTICATION_BACKENDS = ('account.auth_backends.EmailAuthenticationBackend',
                           'django.contrib.auth.backends.ModelBackend')

# Redis connection for syncing user accounts with Varnish
REDIS_DB_HOST = config.get('REDIS_DB_HOST')
REDIS_DB_PORT = config.get('REDIS_DB_PORT')
REDIS_DB_NUMBER = config.get('REDIS_DB_NUMBER')
REDIS_DB_PASSWORD = config.get('REDIS_DB_PASSWORD')
REDIS_SENTINEL_HOSTS = config.get('REDIS_SENTINEL_HOSTS', None)
REDIS_SENTINEL_SET = config.get('REDIS_SENTINEL_SET')

EMAIL_BACKEND = "mailer.backend.DbBackend"
# Configurable email port, to make it easier to develop email sending
EMAIL_PORT = config.get('EMAIL_PORT', 25)

# The name of this api in the redis api management db
REDIS_API_NAME = config.get('REDIS_API_NAME')

# Should the API be restricted to users with API Keys only?
# Note: you can still have api keys and set rate limits on them independently
# of this setting
API_RESTRICT = config.get('API_RESTRICT')

# Should the API be throttled?
API_THROTTLE = config.get('API_THROTTLE')

# How long a time period should the api rate limiter counts hits over (seconds)
API_THROTTLE_COUNTER_TIME = config.get('API_THROTTLE_COUNTER_TIME')

# How many hits during the API_RATE_LIMIT_COUNTER_TIME can a single user make
# by default?
# Note: you can still set limits, or have no limit at all, for individual api
# keys or IP addresses indepent of this setting
API_THROTTLE_DEFAULT_LIMIT = config.get('API_THROTTLE_DEFAULT_LIMIT')

# How long should users who go over the rate limit be blocked for? (Seconds)
API_THROTTLE_BLOCK_TIME = config.get('API_THROTTLE_BLOCK_TIME')

# What is the default quota limit? As above with rate limiting, this can be
# varied per key or IP address.
API_QUOTA_DEFAULT_LIMIT = config.get('API_QUOTA_DEFAULT_LIMIT')

# Potentially load in extra file of IP addresses
MAPIT_RATE_LIMIT_FILE = config.get('RATE_LIMIT_FILE')
if MAPIT_RATE_LIMIT_FILE:
    try:
        with open(MAPIT_RATE_LIMIT_FILE, 'r') as fp:
            MAPIT_RATE_LIMIT_FILE = yaml.load(fp, Loader=yaml.SafeLoader)
            if isinstance(MAPIT_RATE_LIMIT_FILE, dict) and MAPIT_RATE_LIMIT_FILE.get('internal_ips'):
                MAPIT_RATE_LIMIT['ips'] += MAPIT_RATE_LIMIT_FILE['internal_ips']['ipv4']
                MAPIT_RATE_LIMIT['ips'] += MAPIT_RATE_LIMIT_FILE['internal_ips']['ipv6']
    except:
        MAPIT_RATE_LIMIT_FILE = None

# A list of api keys or IP addresses to exclude from rate limiting
# Take this from Mapit's existing setting for now
API_THROTTLE_UNLIMITED = MAPIT_RATE_LIMIT.get('ips', []) + MAPIT_RATE_LIMIT.get('user_agents', [])

STRIPE_SECRET_KEY = config.get('STRIPE_SECRET_KEY')
STRIPE_PUBLIC_KEY = config.get('STRIPE_PUBLIC_KEY')
STRIPE_API_VERSION = config.get('STRIPE_API_VERSION')
STRIPE_TAX_RATE = config.get('STRIPE_TAX_RATE')

# Bulk lookup
MAX_RETRIES = 3
RETRY_INTERVAL = 0
BULK_LOOKUP_AMOUNT = config.get('BULK_LOOKUP_AMOUNT')
BULK_LOOKUP_PRICE_ID = config.get('BULK_LOOKUP_PRICE_ID')

# API subscriptions
PRICING = [
    {'plan': 'mapit-10k-v', 'price': 20, 'calls': '10,000'},
    {'plan': 'mapit-100k-v', 'price': 100, 'calls': '100,000'},
    {'plan': 'mapit-0k-v', 'price': 300, 'calls': '0'},
]
