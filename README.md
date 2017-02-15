MapIt GB
========

This repository houses a Django project which runs
http://mapit.mysociety.org, mySociety's administrative boundary tool for the
UK.

If you're looking to create a MapIt in your country, work on any of the
underlying code, or re-use it as an app in another Django project, you
probably want https://github.com/mysociety/mapit.

This repository is only for the Django project that uses and deploys MapIt
in a specific way for mapit.mysociety.org, so that we can include some
specific additions that other re-users of MapIt may not want.

Local Development
-----------------
There's a Vagrantfile which will install a fully working dev environment for
you.

Local API Key Testing
---------------------
The Vagrantfile installs Redis, Vagrant, libvmod-redis, our varnish-apikey
library and copies some example VCL files into /etc/varnish in order to do
basic api key checking.

Varnish is setup to listen on 6081, and configures one backend service for the
Django dev server on 8000. Both are forwarded through the vagrant
box, so you can access http://localhost:6081 for Varnish cached version, or
http://localhost:8000 for the unfettered Django.

With the default config file, access to the API aspects of MapIt (e.g.
non-html versions of any of the query endpoints) both requires api keys and
throttles access. You can change this by tweaking the settings in
conf/general.yml and then running `python manage.py api_keys_restrict_api`
and/or `python manage.py api_keys_throttle_api` to sync the settings to Redis.

In order to test the site with an api key, you need to register and confirm a
user account, on confirmation, the api key for that account will be synced to
Redis automatically and so you should have access

### Interrogating Redis
Using the Redis CLI, you can find things out about your api and keys, for
example:

- Does the API require keys? `GET api:mapit:restricted`
- Can my key access the api? `GET key:<key>:api:mapit` (Returns user ID)
- Does the API throttle requests? `GET api:mapit:throttled`
- How long will people be blocked for if they exceed the throttle limit? `GET api:mapit:blocked:time`
- How long a window will we count requests over? `GET api:mapit:counter:time`
- How many requests can they make in that window by default? `GET api:mapit:default_max`
- How many requests can a specific key make to the api? `GET key:<key>:ratelimit:mapit:max` ("0" means no limit)
- Is my key blocked? `GET key:<key>:ratelimit:mapit:blocked` ("1" means it's blocked)
- How much longer is it blocked for? `TTL key:<key>:ratelimit:mapit:blocked`
- How many hits have I made in the current count window? `GET key:<key>:ratelimit:mapit:count`
- How long until the count window resets? `TTL key:<key>:ratelimit:mapit:reset`

- What is the user's quota limit? `GET user:<user>:quota:mapit:max`
- What is the user's quota count? `GET user:<user>:quota:mapit:count`
- Is the user blocked for exceeding quota? `GET user:<user>:quota:mapit:blocked`
