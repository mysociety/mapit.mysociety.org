from django.urls import path

from .views import WizardView, FinishedView

urlpatterns = [
    path('', WizardView.as_view(), name='home'),
    path('<int:pk>/<token>', FinishedView.as_view(), name='finished'),
]
