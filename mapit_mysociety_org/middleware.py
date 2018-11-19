from .multidb import use_primary

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
