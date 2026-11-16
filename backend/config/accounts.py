from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_http_methods

from .access import ADMIN_GROUP, MANAGED_GROUPS, OPERATOR_GROUP, ROLE_GROUPS, auth_data, user_role
from .passwords import MAX_PASSWORD_LENGTH

PAGE_SIZE = 50


class AccountError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


def failure(error):
    return JsonResponse({"detail": error.message}, status=error.status)


def require_admin(user):
    if not user.is_authenticated:
        raise AccountError("Inicie sesión para continuar.", 401)
    if user_role(user) != "administrator":
        raise AccountError("Se requiere el rol Administrador.", 403)


@sensitive_variables()
def payload(request, required):
    if request.content_type != "application/json":
        raise AccountError("Se requiere una solicitud JSON.", 415)
    try:
        data = auth_data(request)
        if not isinstance(data, dict) or set(data) != required:
            raise ValueError
        for value in data.values():
            if type(value) not in (str, bool):
                raise ValueError
            if isinstance(value, str):
                value.encode("utf-8")
                if "\0" in value:
                    raise ValueError
        return data
    except RequestDataTooBig:
        raise AccountError("Solicitud demasiado grande.", 413) from None
    except (ValueError, TypeError, RecursionError):
        raise AccountError("Revise los campos de la cuenta.", 400) from None


def describe(user):
    groups = {group.name for group in user.groups.all()}
    role = "administrator" if user.is_superuser else next(
        (role for role, group in ROLE_GROUPS.items() if group in groups),
        "viewer" if OPERATOR_GROUP in groups else None,
    )
    return {
        "id": user.pk,
        "username": user.get_username(),
        "display_name": user.get_full_name(),
        "role": role,
        "is_active": user.is_active,
        "role_review_required": role == "viewer" and OPERATOR_GROUP in groups,
        "protected": user.is_staff or user.is_superuser,
    }


def lock_directory(request):
    # All directory writes acquire the same PostgreSQL row lock before checking
    # the actor and the active administrator count.
    Group.objects.select_for_update().get(name=ADMIN_GROUP)
    actor = get_user_model().objects.filter(pk=request.user.pk).first()
    if actor is None:
        raise AccountError("Inicie sesión para continuar.", 401)
    require_admin(actor)
    if actor.password != request.user.password:
        raise AccountError("La sesión cambió. Vuelva a iniciar sesión.", 401)
    return actor


def assign_role(user, role):
    current = list(user.groups.filter(name__in=MANAGED_GROUPS))
    user.groups.remove(*current)
    group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[role])
    user.groups.add(group)


def validate_role_state(data):
    if data["role"] not in ROLE_GROUPS or type(data["is_active"]) is not bool:
        raise AccountError("Seleccione un rol y un estado válidos.")


@sensitive_variables()
def save_password(user, password):
    if not isinstance(password, str) or not 0 < len(password) <= MAX_PASSWORD_LENGTH:
        raise AccountError(f"La contraseña debe tener hasta {MAX_PASSWORD_LENGTH} caracteres.")
    try:
        validate_password(password, user)
    except ValidationError as error:
        raise AccountError(" ".join(error.messages)) from None
    user.set_password(password)


def editable_target(actor, pk):
    target = get_user_model().objects.select_for_update().filter(pk=pk).first()
    if target is None:
        raise AccountError("Cuenta no encontrada.", 404)
    if target.pk == actor.pk:
        raise AccountError("Gestiona tu contraseña en Mi cuenta. El rol y el estado propios no se pueden cambiar aquí.", 409)
    if target.is_staff or target.is_superuser:
        raise AccountError("Esta cuenta está gestionada en Django.", 409)
    return target


@require_http_methods(["GET", "POST"])
@csrf_protect
@sensitive_variables()
def account_collection(request):
    try:
        require_admin(request.user)
        users = get_user_model().objects
        if request.method == "GET":
            after = request.GET.get("after", "0")
            if not after.isascii() or not after.isdecimal() or len(after) > 18:
                raise AccountError("Página inválida.")
            rows = list(users.filter(pk__gt=int(after)).order_by("pk").prefetch_related("groups")[:PAGE_SIZE + 1])
            return JsonResponse({
                "accounts": [describe(user) for user in rows[:PAGE_SIZE]],
                "next": rows[PAGE_SIZE - 1].pk if len(rows) > PAGE_SIZE else None,
            })
        data = payload(request, {"username", "display_name", "role", "is_active", "password"})
        validate_role_state(data)
        username, name = data["username"], data["display_name"]
        if not isinstance(username, str) or not isinstance(name, str):
            raise AccountError("Ingrese un usuario y un nombre visible válidos.")
        username = users.model.normalize_username(username.strip())
        name = name.strip()
        if not 0 < len(username) <= 150 or not 0 < len(name) <= 150 or not name.isprintable():
            raise AccountError("Ingrese un usuario y un nombre visible de hasta 150 caracteres.")
        with transaction.atomic():
            lock_directory(request)
            if users.filter(username__iexact=username).exists():
                raise AccountError("Ya existe una cuenta con ese usuario.", 409)
            user = users.model(username=username, first_name=name, is_active=data["is_active"])
            user._meta.get_field("username").run_validators(username)
            save_password(user, data["password"])
            user.save(force_insert=True)
            assign_role(user, data["role"])
        return JsonResponse(describe(user), status=201)
    except AccountError as error:
        return failure(error)
    except ValidationError:
        return failure(AccountError("Use letras, números o los signos @ . + - _ para el usuario."))
    except IntegrityError:
        return failure(AccountError("Ya existe una cuenta con ese usuario.", 409))


@require_http_methods(["PATCH"])
@csrf_protect
@sensitive_variables()
def account_detail(request, pk):
    try:
        require_admin(request.user)
        data = payload(request, {"role", "is_active"})
        validate_role_state(data)
        with transaction.atomic():
            actor = lock_directory(request)
            user = editable_target(actor, pk)
            if user_role(user) == "administrator" and (data["role"] != "administrator" or not data["is_active"]):
                another = get_user_model().objects.filter(is_active=True).filter(
                    Q(is_superuser=True) | Q(groups__name=ADMIN_GROUP)
                ).exclude(pk=user.pk).exists()
                if not another:
                    raise AccountError("Debe quedar al menos un administrador activo.", 409)
            user.is_active = data["is_active"]
            user.save(update_fields=["is_active"])
            assign_role(user, data["role"])
        return JsonResponse(describe(user))
    except AccountError as error:
        return failure(error)


@require_http_methods(["POST"])
@csrf_protect
@sensitive_variables()
def account_password(request, pk):
    try:
        require_admin(request.user)
        data = payload(request, {"password"})
        with transaction.atomic():
            actor = lock_directory(request)
            user = editable_target(actor, pk)
            save_password(user, data["password"])
            user.save(update_fields=["password"])
        return JsonResponse(describe(user))
    except AccountError as error:
        return failure(error)
