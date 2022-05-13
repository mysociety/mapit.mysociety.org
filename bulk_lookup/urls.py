from django.urls import path

from .views import AjaxConfirmView, WizardView, FinishedView

urlpatterns = [
    path('', WizardView.as_view(), name='home'),
    path('ajax-confirm', AjaxConfirmView, name='ajax-confirm'),
    path('<int:pk>/<token>', FinishedView.as_view(), name='finished'),
]
