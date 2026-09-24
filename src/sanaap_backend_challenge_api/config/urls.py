"""Project URL configuration."""

from django.contrib import admin
from django.urls import include, path

from sanaap_backend_challenge_api.config.views import health

urlpatterns = [
    path("api/", include("sanaap_backend_challenge_api.documents.urls")),
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    path("api/health/", health, name="health"),
]
