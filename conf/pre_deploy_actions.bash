#!/bin/bash

# abort on any errors
set -e

# check that we are in the expected directory
cd "$(dirname $BASH_SOURCE)"/..

# Some env variables used during development seem to make things break - set
# them back to the defaults which is what they would have on the servers.
PYTHONDONTWRITEBYTECODE=""

# create the virtual environment
virtualenv_args=""
virtualenv_dir='.venv'
virtualenv_activate="$virtualenv_dir/bin/activate"

if [ ! -f "$virtualenv_activate" ]
then
    virtualenv $virtualenv_args $virtualenv_dir
fi

source $virtualenv_activate

# Install GDAL, correct version, right headers
gdal_version=$(gdal-config --version)
# stretch version of GDAL doesn't have matching pypi version
if [ $gdal_version = "2.1.2" ]; then gdal_version="2.1.3"; fi
C_INCLUDE_PATH=/usr/include/gdal CPLUS_INCLUDE_PATH=/usr/include/gdal pip install GDAL==$gdal_version

# Install all the (other) packages
pip install -r requirements.txt

# make sure that there is no old code (the .py files may have been git deleted)
find . -name '*.pyc' -delete

# Compile CSS
bin/mapit_make_css

# Make a copy of the previous static directory to maintain any cached links
if [[ ! -d .static && -d ../mapit.mysociety.org/.static ]]
then
    cp --archive ../mapit.mysociety.org/.static .static
fi
# gather all the static files in one place
python manage.py collectstatic --noinput --link

# Make sure the Redis api key checking/throttling is set up as-per the config
# settings
python manage.py api_keys_restrict_api
python manage.py api_keys_throttle_api
python manage.py subscription_default_quota
