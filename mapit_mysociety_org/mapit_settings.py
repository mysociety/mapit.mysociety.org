import importlib
import os
import yaml

# Path to here is something like
# .../<repo>/<project_name>/settings.py
PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)
PARENT_DIR = os.path.dirname(BASE_DIR)

# The mySociety deployment system works by having a conf directory at the root
# of the repo, containing a general.yml file of options. Use that file if
# present. Obviously you can just edit any part of this file, it is a normal
# Django settings.py file.
try:
    with open(os.path.join(BASE_DIR, 'conf', 'general.yml'), 'r') as fp:
        config = yaml.safe_load(fp)
except:
    config = {}

# An EPSG code for what the areas are stored as, e.g. 27700 is OSGB, 4326 for
# WGS84. Optional, defaults to 4326.
MAPIT_AREA_SRID = int(config.get('AREA_SRID', 4326))

# Set this to the maximum distance (in AREA_SRID units) allowed for the within
# parameter to the point call. Optional, defaults to 0 (off).
MAPIT_WITHIN_MAXIMUM = float(config.get('WITHIN_MAXIMUM', 0))
if MAPIT_WITHIN_MAXIMUM.is_integer():
    MAPIT_WITHIN_MAXIMUM = int(MAPIT_WITHIN_MAXIMUM)

# Country is currently one of GB, NO, IT, KE, SA, or ZA.
# Optional; country specific things won't happen if not set.
MAPIT_COUNTRY = config.get('COUNTRY', '')

# A dictionary of IP addresses, User Agents, or functions that should be
# excluded from rate limiting. Optional.
MAPIT_RATE_LIMIT = config.get('RATE_LIMIT', {})

# A GA code for analytics
GOOGLE_ANALYTICS = config.get('GOOGLE_ANALYTICS', '')

# Django settings for mapit project.

DEBUG = config.get('DEBUG', True)

# (Note that even if DEBUG is true, output_json still sets a
# Cache-Control header with max-age of 28 days.)
if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        }
    }
    CACHE_MIDDLEWARE_SECONDS = 0
else:
    try:
        import pylibmc  # noqa
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.memcached.PyLibMCCache',
                'LOCATION': '127.0.0.1:11211',
                'TIMEOUT': 86400,
            }
        }
    except ImportError:
        pass
    CACHE_MIDDLEWARE_SECONDS = 86400
    CACHE_MIDDLEWARE_KEY_PREFIX = config.get('MAPIT_DB_NAME')

if config.get('BUGS_EMAIL'):
    SERVER_EMAIL = config['BUGS_EMAIL']
    ADMINS = (
        ('mySociety bugs', config['BUGS_EMAIL']),
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': config.get('MAPIT_DB_NAME', 'mapit'),
        'USER': config.get('MAPIT_DB_USER', 'mapit'),
        'PASSWORD': config.get('MAPIT_DB_PASS', ''),
        'HOST': config.get('MAPIT_DB_HOST', ''),
        'PORT': config.get('MAPIT_DB_PORT', ''),
    }
}

# Make this unique, and don't share it with anybody.
SECRET_KEY = config.get('DJANGO_SECRET_KEY', '')

ALLOWED_HOSTS = ['*']

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
if MAPIT_COUNTRY == 'GB':
    TIME_ZONE = 'Europe/London'
    LANGUAGE_CODE = 'en-gb'
    POSTCODES_AVAILABLE = PARTIAL_POSTCODES_AVAILABLE = True
elif MAPIT_COUNTRY == 'NO':
    TIME_ZONE = 'Europe/Oslo'
    LANGUAGE_CODE = 'no'
    POSTCODES_AVAILABLE = PARTIAL_POSTCODES_AVAILABLE = True
elif MAPIT_COUNTRY == 'IT':
    TIME_ZONE = 'Europe/Rome'
    LANGUAGE_CODE = 'it'
    POSTCODES_AVAILABLE = True
    PARTIAL_POSTCODES_AVAILABLE = False
elif MAPIT_COUNTRY == 'ZA':
    TIME_ZONE = 'Africa/Johannesburg'
    LANGUAGE_CODE = 'en-za'
    POSTCODES_AVAILABLE = PARTIAL_POSTCODES_AVAILABLE = False
else:
    TIME_ZONE = 'Europe/London'
    LANGUAGE_CODE = 'en'
    POSTCODES_AVAILABLE = True
    PARTIAL_POSTCODES_AVAILABLE = False

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = False

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/var/www/example.com/media/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://example.com/media/", "http://media.example.com/"
MEDIA_URL = ''

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/var/www/example.com/static/"
STATIC_ROOT = os.path.join(BASE_DIR, '.static')

# URL prefix for static files.
# Example: "http://example.com/static/", "http://static.example.com/"
STATIC_URL = '/static/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # 'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# UpdateCacheMiddleware does ETag setting, and
# ConditionalGetMiddleware does ETag checking.
# So we don't want this flag, which runs very
# similar ETag code in CommonMiddleware.
USE_ETAGS = False

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.http.ConditionalGetMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
    'mapit.middleware.JSONPMiddleware',
    'mapit.middleware.ViewExceptionMiddleware',
]

ROOT_URLCONF = 'project.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'project.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'OPTIONS': {
        'context_processors': (
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'mapit.context_processors.country',
            'mapit.context_processors.analytics',
        ),
        # List of callables that know how to import templates from various sources.
        'loaders': (
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ),
    },
}]
if not DEBUG:
    TEMPLATES[0]['OPTIONS']['loaders'] = (
        ('django.template.loaders.cached.Loader', TEMPLATES[0]['OPTIONS']['loaders']),
    )

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.admin',
    'django.contrib.gis',
    'django.contrib.staticfiles',
    'mapit',
]

if MAPIT_COUNTRY:
    c = 'mapit_%s' % MAPIT_COUNTRY.lower()
    print(c)
    import sys
    print(sys.path)
    print(sys.meta_path)
    c_spec = importlib.util.find_spec(c)
    if c_spec is not None:
        # Put before 'mapit', so country templates take precedence
        INSTALLED_APPS.insert(INSTALLED_APPS.index('mapit'), c)
        print(INSTALLED_APPS)

DATE_FORMAT = 'j F Y'
