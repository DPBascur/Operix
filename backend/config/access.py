"""Política mínima de acceso de personas. La publicación interna usa otro canal."""

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.cache import add_never_cache_headers
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission

import json

SAFETY_GROUP = "Responsable de seguridad"
OPERATOR_GROUP = "Usuario"


def user_role(user):
    if not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return "administrator"
    groups = set(user.groups.filter(name__in=(SAFETY_GROUP, OPERATOR_GROUP)).values_list("name", flat=True))
    if SAFETY_GROUP in groups:
        return "safety_lead"
    if OPERATOR_GROUP in groups:
        return "operator"
    return None


def request_role(request):
    if not hasattr(request, "_operix_role"):
        request._operix_role = user_role(request.user)
    return request._operix_role


class BrowserSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"


class HasOperixRole(BasePermission):
    def has_permission(self, request, view):
        return request_role(request) is not None


class CanReviewEvents(BasePermission):
    def has_permission(self, request, view):
        return request_role(request) in {"administrator", "safety_lead"}


class CanAnalyze(BasePermission):
    def has_permission(self, request, view):
        return request_role(request) in {"administrator", "operator"}


def session_response(request, *, error=None, status=200):
    role = user_role(request.user)
    user = {"username": request.user.get_username(), "role": role} if role else None
    data = {"user": user, "csrf_token": get_token(request)}
    if error:
        data["detail"] = error
    response = JsonResponse(data, status=status)
    add_never_cache_headers(response)
    return response


@require_http_methods(["GET"])
def session_view(request):
    return session_response(request)


@require_http_methods(["POST"])
@csrf_protect
def login_view(request):
    try:
        data = json.loads(request.body)
        username, password = data["username"], data["password"]
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError
        if not 0 < len(username.strip()) <= 150 or not 0 < len(password) <= 4096:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        return session_response(request, error="Ingrese usuario y contraseña válidos.", status=400)
    user = authenticate(request, username=username.strip(), password=password)
    if user is None or user_role(user) is None:
        return session_response(request, error="Usuario o contraseña incorrectos, o cuenta sin acceso.", status=401)
    login(request, user)
    request.session.set_expiry(28800)
    return session_response(request)


@require_http_methods(["POST"])
@csrf_protect
def logout_view(request):
    logout(request)
    return session_response(request)
