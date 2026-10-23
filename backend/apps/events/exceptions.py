"""Errores de dependencias sin exponer SQL, credenciales ni rutas al cliente."""

import logging

from django.db import DatabaseError
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


logger = logging.getLogger(__name__)


class DependencyUnavailable(APIException):
    status_code = 503
    default_detail = "No se pudo completar la operación. Revise la disponibilidad del servicio e inténtelo nuevamente."
    default_code = "dependency_unavailable"


def api_exception_handler(exc, context):
    if isinstance(exc, (DatabaseError, OSError)):
        # La respuesta no propaga el texto de excepciones del driver/storage.
        logger.warning("Dependencia no disponible: %s", type(exc).__name__)
        return exception_handler(DependencyUnavailable(), context)
    return exception_handler(exc, context)
