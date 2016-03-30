from django.views.generic import ListView

from .models import APIKey


class APIKeyListView(ListView):
    template_name = 'api_keys/api_key_list.html'
    context_object_name = 'api_keys'
    model = APIKey

    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user)
