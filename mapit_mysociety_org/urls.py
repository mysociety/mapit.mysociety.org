from django.conf.urls import include, url
from django.contrib import admin
from django.views.defaults import page_not_found

from django.shortcuts import render

from .views import LoginView, LogoutView, SignupView, ConfirmEmailView

urlpatterns = [
    url(r'^changelog$', render, {'template_name': 'changelog.html'}, 'mapit_changelog'),
    url(r'^', include('mapit.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r"^account/api_keys/", include("api_keys.urls")),
    # Turn off the settings url from the account app, as we don't want it.
    url(r"^account/settings/", page_not_found),
    # Override the login and signup views from the account app, so we can use
    # our versions which use an email address instead of a username.
    url(r"^account/signup/$", SignupView.as_view(), name="account_signup"),
    url(r"^account/login/$", LoginView.as_view(), name="account_login"),
    url(r"^account/logout/$", LogoutView.as_view(), name="account_logout"),
    # Override the confirm_email view from the account app, so we can sign
    # people in immediately after they confirm.
    url(r"^account/confirm_email/(?P<key>\w+)/$", ConfirmEmailView.as_view(), name="account_confirm_email"),
    url(r"^account/", include("account.urls")),
]
