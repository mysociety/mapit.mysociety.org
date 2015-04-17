from django.conf.urls import include, url
from django.contrib import admin
from django.views.defaults import page_not_found
admin.autodiscover()

urlpatterns = [
    url(r'^', include('mapit.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r"^account/api_keys/", include("api_keys.urls")),
    # Turn off the settings url from the account app, as we don't want it.
    url(r"^account/settings/", page_not_found),
    url(r"^account/", include("account.urls")),
]
