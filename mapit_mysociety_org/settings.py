import os

# Import MapIt's settings
from mapit_settings import *

# Update a couple of things to suit our changes

INSTALLED_APPS.extend(['django.contrib.sites', 'account', 'api_keys', 'subscriptions'])

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

MIDDLEWARE_CLASSES.extend([
    'django.middleware.csrf.CsrfViewMiddleware',
    "account.middleware.LocaleMiddleware",
    "account.middleware.TimezoneMiddleware",
])

old_staticfiles_dirs = STATICFILES_DIRS
STATICFILES_DIRS = old_staticfiles_dirs + (
    os.path.join(BASE_DIR, 'static'),
    os.path.join(BASE_DIR, 'theme'),
)

# New mapit.mysociety.org settings

# Config for Django's sites framework, needed so that we can send emails from
# django-user-accounts with fully qualifed urls in
SITE_ID = 1
SITE_BASE_URL = config.get('SITE_BASE_URL', '')
SITE_NAME = config.get('SITE_NAME', 'MapIt')

LOGIN_URL = '/account/login'

# django-user-accounts settings
# Emails must be unique because we use them as usernames
ACCOUNT_EMAIL_UNIQUE = True
CONTACT_EMAIL = config.get('CONTACT_EMAIL', '')
DEFAULT_FROM_EMAIL = CONTACT_EMAIL
ACCOUNT_USER_DISPLAY = lambda user: user.email
ACCOUNT_LOGOUT_REDIRECT_URL = 'mapit_index'
# Enable authentication by email address not username
AUTHENTICATION_BACKENDS = ('account.auth_backends.EmailAuthenticationBackend',
                           'django.contrib.auth.backends.ModelBackend')

# Redis connection for syncing user accounts with Varnish
REDIS_DB_HOST = config.get('REDIS_DB_HOST')
REDIS_DB_PORT = config.get('REDIS_DB_PORT')
REDIS_DB_NUMBER = config.get('REDIS_DB_NUMBER')
REDIS_DB_PASSWORD = config.get('REDIS_DB_PASSWORD')

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

# A list of api keys or IP addresses to exclude from rate limiting
# Take this from Mapit's existing setting for now
API_THROTTLE_UNLIMITED = MAPIT_RATE_LIMIT

STRIPE_SECRET_KEY = config.get('STRIPE_SECRET_KEY')
STRIPE_PUBLIC_KEY = config.get('STRIPE_PUBLIC_KEY')

PRICING = [
    {'plan': 'mapit-10k', 'price': 20, 'calls': '10,000'},
    {'plan': 'mapit-100k', 'price': 100, 'calls': '100,000'},
    {'plan': 'mapit-0k', 'price': 300, 'calls': '0'},
]
