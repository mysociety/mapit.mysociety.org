from django.conf.urls import url
from django.contrib.auth.decorators import login_required

from .views import APIKeyDetailView

urlpatterns = [
    url(r'^key', login_required(APIKeyDetailView.as_view()), name="api_keys_key"),
]
