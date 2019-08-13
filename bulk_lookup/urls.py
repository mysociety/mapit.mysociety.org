from django.conf.urls import url

from .views import AjaxConfirmView, WizardView, FinishedView

urlpatterns = [
    url(r'^$', WizardView.as_view(), name='home'),
    url(r'^ajax-confirm$', AjaxConfirmView, name='ajax-confirm'),
    url(r'^(?P<pk>\d+)/(?P<token>.+)$', FinishedView.as_view(), name='finished'),
]
