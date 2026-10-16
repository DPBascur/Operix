from django.contrib import admin
from django.urls import include, path

from apps.events.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.analysis.urls")),
]
