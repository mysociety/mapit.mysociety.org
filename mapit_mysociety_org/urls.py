from django.urls import include, path
from django.contrib import admin
from django.views.generic.base import RedirectView

from django.shortcuts import render

from .views import LoginView, LogoutView, SignupView, ConfirmEmailView

urlpatterns = [
    path('changelog', render, {'template_name': 'changelog.html'}, 'mapit_changelog'),
    path('', include('mapit.urls')),
    path('contact', render, {'template_name': 'mapit/contact.html'}, 'mapit_contact'),
    path('pricing/', render, {'template_name': 'pricing.html'}, 'mapit_pricing'),
    path('legal/', render, {'template_name': 'mapit/licensing.html'}, 'mapit_legal'),
    path('privacy/', render, {'template_name': 'mapit/privacy.html'}, 'mapit_privacy'),
    path('docs/', render, {'template_name': 'docs.html'}, 'mapit_docs'),
    path('admin', RedirectView.as_view(url='admin/', permanent=True)),
    path('admin/', admin.site.urls),
    path("bulk/", include("bulk_lookup.urls")),
    path("account/api_keys/", include("api_keys.urls")),
    path("account/subscription", include("subscriptions.urls")),
    # Override the login and signup views from the account app, so we can use
    # our versions which use an email address instead of a username.
    path("account/signup/", SignupView.as_view(), name="account_signup"),
    path("account/login/", LoginView.as_view(), name="account_login"),
    path("account/logout/", LogoutView.as_view(), name="account_logout"),
    # Override the confirm_email view from the account app, so we can sign
    # people in immediately after they confirm.
    path("account/confirm_email/<key>/", ConfirmEmailView.as_view(), name="account_confirm_email"),
    path("account/", RedirectView.as_view(pattern_name='subscription', permanent=True)),
    path("account/", include("account.urls")),
]
