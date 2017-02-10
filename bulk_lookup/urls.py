from django.conf.urls import url

from .views import WizardView, FinishedView

urlpatterns = [
    url(r'^$', WizardView.as_view(), name='home'),
    url(r'^(?P<pk>\d+)/(?P<token>.+)$', FinishedView.as_view(), name='finished'),
]
