from django.urls import path
from django.contrib.auth.decorators import login_required

from .views import APIKeyListView, APIKeyDeleteView, APIKeyCreateView

urlpatterns = [
    path(
        'keys',
        login_required(APIKeyListView.as_view()),
        name="api_keys_keys"
    ),
    path(
        'create',
        login_required(APIKeyCreateView.as_view()),
        name="api_keys_create_key"
    ),
    path(
        '<int:pk>/delete',
        login_required(APIKeyDeleteView.as_view()),
        name="api_keys_delete_key"
    )
]
