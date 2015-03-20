from django.conf.urls import include, url
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
admin.autodiscover()

urlpatterns = [
    url(r'^', include('mapit.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r"^account/", include("account.urls")),
]
