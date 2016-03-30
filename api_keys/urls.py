from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from .views import APIKeyListView

urlpatterns = [
    url(
        r'^keys',
        login_required(APIKeyListView.as_view()),
        name="api_keys_keys"
    ),
]
