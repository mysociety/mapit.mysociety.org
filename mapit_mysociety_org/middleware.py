from functools import partial
from django.utils.encoding import force_bytes
from six.moves import map
from .multidb import use_primary
from api_keys.models import APIKey

READ_METHODS = frozenset(['GET', 'HEAD', 'OPTIONS', 'TRACE'])


def force_primary_middleware(get_response):
    """On a non-read request (e.g. POST), always use the primary database, and
    set a short-lived cookie. Then on any request made including that cookie,
    also always use the primary database. This is so we don't need to worry
    about any replication lag for reads made immediately after writes, because
    we force those reads to go to the primary."""
    def middleware(request):
        use_primary('primary_forced' in request.COOKIES or request.method not in READ_METHODS)

        response = get_response(request)

        if request.method not in READ_METHODS:
            response.set_cookie('primary_forced', value='y', max_age=10)

        return response

    return middleware


def add_api_key(get_response):
    """If logged in, we want to include the API key in any
    client-side JSON calls (e.g. to plot area on map)."""

    def alter_content(api_key, content):
        key = force_bytes(api_key)
        content = content.replace(b'simplify_tolerance=0.0001', b'simplify_tolerance=0.0001&api_key=' + key)
        content = content.replace(b'data-key=""', b'data-key="' + key + b'"')
        return content

    def middleware(request):
        api_key = None
        if request.user.is_authenticated:
            api_key = APIKey.objects.filter(user=request.user).first()

        response = get_response(request)

        if api_key:
            wrap_content = partial(alter_content, api_key.key)
            if response.streaming:
                response.streaming_content = map(wrap_content, response.streaming_content)
            else:
                response.content = wrap_content(response.content)

        return response

    return middleware
