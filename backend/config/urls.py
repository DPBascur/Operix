from django.contrib import admin
from django.urls import include, path

from apps.events.views import health
from .access import login_view, logout_view, session_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/session/", session_view),
    path("api/v1/auth/login/", login_view),
    path("api/v1/auth/logout/", logout_view),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.analysis.urls")),
]
