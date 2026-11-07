from django.contrib import admin
from django.conf import settings
from django.urls import include, path

from apps.events.views import health
from .access import admin_login_view, admin_password_view, login_view, logout_view, password_view, session_view

urlpatterns = [
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/session/", session_view),
    path("api/v1/auth/login/", login_view),
    path("api/v1/auth/logout/", logout_view),
    path("api/v1/auth/password/", password_view),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.analysis.urls")),
]
if settings.OPERIX_ADMIN_ENABLED:
    urlpatterns += [path("admin/login/", admin_login_view),
                    path("admin/password_change/", admin_password_view), path("admin/", admin.site.urls)]
