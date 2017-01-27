from django.views.decorators.cache import never_cache


class NeverCacheMixin(object):
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(NeverCacheMixin, cls).as_view(**initkwargs)
        return never_cache(view)
