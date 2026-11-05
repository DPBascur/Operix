"""Frontera de escritura entre el Backend y el publicador interno."""

import hmac
import os

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def require_event_publisher(request):
    if not settings.EVENT_POST_ENABLED:
        raise PermissionDenied("POST no está habilitado en este entorno.")
    token = settings.OPERIX_EVENT_PUBLISH_TOKEN
    authorization = request.headers.get("Authorization", "")
    if not token or not hmac.compare_digest(authorization.encode("utf-8"), f"Bearer {token}".encode("utf-8")):
        raise PermissionDenied("Publicador de eventos no autorizado.")


def event_publisher_environment():
    return {**os.environ, "OPERIX_EVENT_PUBLISH_TOKEN": settings.OPERIX_EVENT_PUBLISH_TOKEN}
