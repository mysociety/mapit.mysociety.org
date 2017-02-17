#!/bin/bash

# abort on any errors
set -e

# check that we are in the expected directory
cd "$(dirname $BASH_SOURCE)"/..

# Some env variables used during development seem to make things break - set
# them back to the defaults which is what they would have on the servers.
PYTHONDONTWRITEBYTECODE=""

# create the virtual environment; we always want system packages
virtualenv_args="--system-site-packages"
virtualenv_dir='.venv'
virtualenv_activate="$virtualenv_dir/bin/activate"

if [ ! -f "$virtualenv_activate" ]
then
    virtualenv $virtualenv_args $virtualenv_dir
fi

source $virtualenv_activate

# Upgrade pip to a secure version
# curl -L -s https://raw.github.com/pypa/pip/master/contrib/get-pip.py | python
# Revert to the line above once we can get a newer setuptools from Debian, or
# pip ceases to need such a recent one.
curl -L -s https://raw.github.com/mysociety/commonlib/master/bin/get_pip.bash | bash
# Improve SSL behaviour
pip install 'pyOpenSSL>=0.14'

# Install all the packages
pip install -r requirements.txt

# make sure that there is no old code (the .py files may have been git deleted)
find . -name '*.pyc' -delete

# Compile CSS
bin/mapit_make_css

# gather all the static files in one place
python manage.py collectstatic --noinput --link

# Configure the default site's base url, so that link-building using the sites
# framework works.
python manage.py create_default_site

# Make sure the Redis api key checking/throttling is set up as-per the config
# settings
python manage.py api_keys_restrict_api
python manage.py api_keys_throttle_api
python manage.py subscription_default_quota
