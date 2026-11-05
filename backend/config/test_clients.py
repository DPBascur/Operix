"""Identidad de prueba para regresiones que no ejercitan login."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


def administrator_client():
    client = APIClient()
    client.force_authenticate(user=get_user_model()(pk=1, is_superuser=True))
    return client
