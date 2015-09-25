from django.conf.urls import include, url
from django.contrib import admin
from django.views.defaults import page_not_found
admin.autodiscover()

from .views import LoginView, SignupView

urlpatterns = [
    url(r'^', include('mapit.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r"^account/api_keys/", include("api_keys.urls")),
    # Turn off the settings url from the account app, as we don't want it.
    url(r"^account/settings/", page_not_found),
    # Override the login and signup views from the account app, so we can use
    # our versions which use an email address instead of a username.
    url(r"^account/signup/$", SignupView.as_view(), name="account_signup"),
    url(r"^account/login/$", LoginView.as_view(), name="account_login"),
    url(r"^account/", include("account.urls")),
]
