"""Política mínima de acceso de personas. La publicación interna usa otro canal."""

import json
from ipaddress import ip_address
from time import time

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import RequestDataTooBig
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token, rotate_token
from django.utils.cache import add_never_cache_headers
from django.utils.crypto import salted_hmac
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission

from .models import LoginBucket
from .passwords import MAX_PASSWORD_LENGTH

SAFETY_GROUP = "Responsable de seguridad"
OPERATOR_GROUP = "Usuario"
LOGIN_PEER_LIMIT = 80
LOGIN_ACCOUNT_LIMIT = 8
LOGIN_DISTRIBUTED_LIMIT = 30
LOGIN_TOTAL_LIMIT = 400
MAX_AUTH_BODY = 32 * 1024
MAX_CURRENT_PASSWORD = 4096


def private_api_responses(get_response):
    def middleware(request):
        response = get_response(request)
        if request.path_info.startswith("/api/v1/") and request.path_info != "/api/v1/health/":
            add_never_cache_headers(response)
        return response
    return middleware


def login_peer(request):
    peer = request.META.get("REMOTE_ADDR", "")
    if peer in settings.OPERIX_TRUSTED_LOGIN_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For", "").rsplit(",", 1)[-1].strip()
        try:
            return str(ip_address(forwarded))
        except ValueError:
            pass
    return peer


@transaction.atomic
def login_retry_after(request, username):
    peer = login_peer(request)
    seconds = settings.OPERIX_LOGIN_WINDOW_SECONDS
    window, elapsed = divmod(int(time()), seconds)
    for scope, identity, limit in (
        ("total", "", LOGIN_TOTAL_LIMIT),
        ("peer", peer, LOGIN_PEER_LIMIT),
        ("account_global", username.casefold(), LOGIN_DISTRIBUTED_LIMIT),
        ("account", f"{peer}\0{username.casefold()}", LOGIN_ACCOUNT_LIMIT),
    ):
        digest = salted_hmac(f"operix.login.{scope}", identity, algorithm="sha256").hexdigest()
        key = f"{scope}:{digest}"
        bucket, _ = LoginBucket.objects.select_for_update().get_or_create(
            key=key, defaults={"window": window, "attempts": 0},
        )
        if bucket.window > window:
            return 1
        if bucket.window != window:
            bucket.window, bucket.attempts = window, 0
        if bucket.attempts >= limit:
            return seconds - elapsed
        bucket.attempts += 1
        bucket.save(update_fields=["window", "attempts"])
        if scope == "total":
            # All attempts lock this row first. The global budget bounds the
            # number of other rows created; remove expired identities here.
            LoginBucket.objects.filter(window__lt=window).exclude(key=key).delete()
    return None


def throttled(request, username):
    retry_after = login_retry_after(request, username)
    if retry_after is None:
        return None
    response = session_response(request, error="Demasiados intentos. Espere antes de volver a intentar.", status=429)
    response["Retry-After"] = str(retry_after)
    return response


@sensitive_variables()
def auth_data(request):
    payload = request.read(MAX_AUTH_BODY + 1)
    if len(payload) > MAX_AUTH_BODY:
        raise RequestDataTooBig
    return json.loads(payload)


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
@sensitive_variables("data", "password")
def login_view(request):
    try:
        data = auth_data(request)
        username, password = data["username"], data["password"]
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError
        if not 0 < len(username.strip()) <= 150 or not 0 < len(password) <= MAX_CURRENT_PASSWORD:
            raise ValueError
        if "\0" in username:
            raise ValueError
        username.encode("utf-8")
        password.encode("utf-8")
    except RequestDataTooBig:
        return session_response(request, error="Solicitud demasiado grande.", status=413)
    except (ValueError, TypeError, KeyError, RecursionError):
        return session_response(request, error="Ingrese usuario y contraseña válidos.", status=400)
    username = username.strip()
    limited = throttled(request, username)
    if limited:
        return limited
    user = authenticate(request, username=username, password=password)
    if user is None or user_role(user) is None:
        return session_response(request, error="Usuario o contraseña incorrectos, o cuenta sin acceso.", status=401)
    login(request, user)
    request.session.set_expiry(28800)
    return session_response(request)


@csrf_protect
@sensitive_post_parameters()
@sensitive_variables("password")
def admin_login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if "\0" in username or len(username) > 150 or len(password) > MAX_CURRENT_PASSWORD:
            return session_response(request, error="Credenciales inválidas.", status=400)
        limited = throttled(request, username)
        if limited:
            return limited
    return admin.site.login(request)


@csrf_protect
@sensitive_post_parameters()
def admin_password_view(request):
    if request.method == "POST" and request.user.is_active and request.user.is_staff:
        limited = throttled(request, request.user.get_username())
        if limited:
            return limited
    return admin.site.password_change(request)


@require_http_methods(["POST"])
@csrf_protect
@sensitive_variables("data", "form", "value")
def password_view(request):
    if user_role(request.user) is None:
        return session_response(request, error="Inicie sesión para continuar.", status=401)
    try:
        data = auth_data(request)
        limits = {"old_password": MAX_CURRENT_PASSWORD, "new_password1": MAX_PASSWORD_LENGTH,
                  "new_password2": MAX_PASSWORD_LENGTH}
        if not isinstance(data, dict) or data.keys() != limits.keys() or any(
            not isinstance(data[field], str) or not 0 < len(data[field]) <= limit
            for field, limit in limits.items()
        ):
            raise ValueError
        for value in data.values():
            value.encode("utf-8")
    except RequestDataTooBig:
        return session_response(request, error="Solicitud demasiado grande.", status=413)
    except (ValueError, TypeError, RecursionError):
        return session_response(request, error="Revise los campos y la longitud de las contraseñas.", status=400)
    limited = throttled(request, request.user.get_username())
    if limited:
        return limited
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
        if user is None or user.password != request.user.password:
            return session_response(request, error="La sesión cambió. Vuelva a iniciar sesión.", status=401)
        form = PasswordChangeForm(user, data)
        if not form.is_valid():
            detail = " ".join(str(message) for errors in form.errors.values() for message in errors)
            return session_response(request, error=detail, status=400)
        user = form.save()
    update_session_auth_hash(request, user)
    rotate_token(request)
    return session_response(request)


@require_http_methods(["POST"])
@csrf_protect
def logout_view(request):
    logout(request)
    return session_response(request)
