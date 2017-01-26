from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from .views import SubscriptionView, SubscriptionUpdateView, SubscriptionCardUpdateView, SubscriptionCancelView

urlpatterns = [
    url(
        r'^$',
        login_required(SubscriptionView.as_view()),
        name="subscription"
    ),
    url(
        r'^/update$',
        login_required(SubscriptionUpdateView.as_view()),
        name="subscription_update"
    ),
    url(
        r'^/update-card$',
        login_required(SubscriptionCardUpdateView.as_view()),
        name="subscription_card_update"
    ),
    url(
        r'^/cancel$',
        login_required(SubscriptionCancelView.as_view()),
        name="subscription_cancel"
    ),
]
