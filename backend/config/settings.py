"""Environment-driven settings for the Operix API."""

import os
import re
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def csv_setting(name: str) -> list[str]:
    return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]


SECRET_KEY = required("DJANGO_SECRET_KEY")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
EVENT_POST_ENABLED = os.environ.get("EVENT_POST_ENABLED", "0") == "1"
OPERIX_EVENT_PUBLISH_TOKEN = os.environ.get("OPERIX_EVENT_PUBLISH_TOKEN", "").strip() or secrets.token_urlsafe(32)
if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", OPERIX_EVENT_PUBLISH_TOKEN):
    raise RuntimeError("OPERIX_EVENT_PUBLISH_TOKEN requiere al menos 32 caracteres URL-safe.")
OPERIX_EVENT_API_BASE_URL = os.environ.get("OPERIX_EVENT_API_BASE_URL", "http://127.0.0.1:8000/api/v1")
ALLOWED_HOSTS = csv_setting("DJANGO_ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = csv_setting("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = csv_setting("CSRF_TRUSTED_ORIGINS")
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = os.environ.get("OPERIX_SECURE_COOKIES", "0") == "1"
SESSION_COOKIE_HTTPONLY = CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = "Lax"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 15}},
    {"NAME": "config.passwords.MaximumPasswordLengthValidator"},
] + [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in ("UserAttributeSimilarityValidator", "CommonPasswordValidator")
]
OPERIX_LOGIN_WINDOW_SECONDS = max(1, int(os.environ.get("OPERIX_LOGIN_WINDOW_SECONDS", "300")))
OPERIX_TRUSTED_LOGIN_PROXIES = csv_setting("OPERIX_TRUSTED_LOGIN_PROXIES")
OPERIX_ADMIN_ENABLED = os.environ.get("OPERIX_ADMIN_ENABLED", "1") == "1"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.analysis",
    "apps.events",
    "config",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "config.access.private_api_responses",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required("POSTGRES_DB"),
        "USER": required("POSTGRES_USER"),
        "PASSWORD": required("POSTGRES_PASSWORD"),
        "HOST": required("POSTGRES_HOST"),
        "PORT": required("POSTGRES_PORT"),
    }
}

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "apps.events.exceptions.api_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": ["config.access.BrowserSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["config.access.HasOperixRole"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
_media_setting = Path(os.environ.get("OPERIX_MEDIA_ROOT", "media"))
MEDIA_ROOT = (_media_setting if _media_setting.is_absolute() else BASE_DIR / _media_setting).resolve()
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
OPERIX_ENGINE_PYTHON = os.environ.get(
    "OPERIX_ENGINE_PYTHON", str(BASE_DIR.parent / "engine/.venv/Scripts/python.exe")
)
OPERIX_PERSON_WEIGHTS = os.environ.get("OPERIX_PERSON_WEIGHTS", "")
OPERIX_FORKLIFT_WEIGHTS = os.environ.get("OPERIX_FORKLIFT_WEIGHTS", "")
OPERIX_ANALYSIS_MAX_UPLOAD_BYTES = int(os.environ.get("OPERIX_ANALYSIS_MAX_UPLOAD_BYTES", str(250 * 1024 * 1024)))
OPERIX_ANALYSIS_MAX_SESSIONS = int(os.environ.get("OPERIX_ANALYSIS_MAX_SESSIONS", "2"))
OPERIX_ANALYSIS_RETENTION_SECONDS = int(os.environ.get("OPERIX_ANALYSIS_RETENTION_SECONDS", "3600"))
OPERIX_ANALYSIS_TIMEOUT_SECONDS = max(1, int(os.environ.get("OPERIX_ANALYSIS_TIMEOUT_SECONDS", "1800")))
OPERIX_CLIPS_ENABLED = os.environ.get("OPERIX_CLIPS_ENABLED", "1") == "1"
OPERIX_CLIP_WINDOW_SECONDS = max(1, min(10, int(os.environ.get("OPERIX_CLIP_WINDOW_SECONDS", "5"))))
OPERIX_CLIP_MAX_BYTES = 12 * 1024 * 1024
OPERIX_CLIP_TOTAL_BYTES = 512 * 1024 * 1024
OPERIX_CLIP_MAX_PER_RUN = 24
OPERIX_DEMO_VIDEO_A = os.environ.get("OPERIX_DEMO_VIDEO_A", "")
OPERIX_DEMO_VIDEO_B = os.environ.get("OPERIX_DEMO_VIDEO_B", "")
OPERIX_DEMO_VIDEO_C = os.environ.get("OPERIX_DEMO_VIDEO_C", "")
