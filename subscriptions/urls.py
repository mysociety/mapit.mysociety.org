from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from .views import SubscriptionView, SubscriptionUpdateView, SubscriptionCancelView

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
        r'^/cancel$',
        login_required(SubscriptionCancelView.as_view()),
        name="subscription_cancel"
    ),
]
