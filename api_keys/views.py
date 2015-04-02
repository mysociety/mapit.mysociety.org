from django.views.generic import DetailView


class APIKeyDetailView(DetailView):
    template_name = 'api_keys/api_key_detail.html'
    context_object_name = 'api_key'

    def get_object(self, queryset=None):
        return self.request.user.api_key
