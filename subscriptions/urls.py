from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from .views import SubscriptionView

urlpatterns = [
    url(
        r'^$',
        login_required(SubscriptionView.as_view()),
        name="subscription"
    ),
]
