from django.core.urlresolvers import reverse_lazy, reverse
from django.views.generic import ListView, DeleteView
from django.views.generic.base import View
from django.http import Http404, HttpResponseRedirect

from .models import APIKey
from mapit_mysociety_org.mixins import NeverCacheMixin


class APIKeyListView(NeverCacheMixin, ListView):
    template_name = 'api_keys/api_key_list.html'
    context_object_name = 'api_keys'
    model = APIKey

    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user)


class APIKeyDeleteView(DeleteView):
    template_name = 'api_keys/api_key_delete_confirm.html'
    context_object_name = 'api_key'
    model = APIKey
    success_url = reverse_lazy('api_keys_keys')

    def get_object(self, queryset=None):
        """ Hook to ensure api_key is owned by request.user. """
        api_key = super(APIKeyDeleteView, self).get_object()
        if not api_key.user == self.request.user:
            raise Http404
        return api_key


class APIKeyCreateView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        APIKey.objects.create(user=request.user, key=APIKey.generate_key())
        return HttpResponseRedirect(reverse('api_keys_keys'))
