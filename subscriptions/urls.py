from django.urls import path
from django.contrib.auth.decorators import login_required

from .views import (
    stripe_hook, InvoicesView, SubscriptionView, SubscriptionUpdateView,
    SubscriptionCardUpdateView, SubscriptionCancelView)

urlpatterns = [
    path(
        '',
        login_required(SubscriptionView.as_view()),
        name="subscription"
    ),
    path(
        '/invoices',
        login_required(InvoicesView.as_view()),
        name="invoices"
    ),
    path(
        '/update',
        login_required(SubscriptionUpdateView.as_view()),
        name="subscription_update"
    ),
    path(
        '/update-card',
        login_required(SubscriptionCardUpdateView.as_view()),
        name="subscription_card_update"
    ),
    path(
        '/cancel',
        login_required(SubscriptionCancelView.as_view()),
        name="subscription_cancel"
    ),
    path(
        '/stripe-hook',
        stripe_hook,
        name="stripe-hook"
    ),
]
