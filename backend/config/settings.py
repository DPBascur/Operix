"""Environment-driven settings for the Operix API."""

import os
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
ALLOWED_HOSTS = csv_setting("DJANGO_ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = csv_setting("CORS_ALLOWED_ORIGINS")

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
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
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
OPERIX_DEMO_VIDEO_A = os.environ.get("OPERIX_DEMO_VIDEO_A", "").strip() or str(
    BASE_DIR.parent / "assets/demo/warehouse_fire_ceiling04.mp4"
)
OPERIX_DEMO_VIDEO_B = os.environ.get("OPERIX_DEMO_VIDEO_B", "").strip() or str(
    BASE_DIR.parent / "assets/demo/forklift_human_nearmiss_ceiling00.mp4"
)
# C se mantiene fuera del repositorio; cada instalación local decide su ruta.
OPERIX_DEMO_VIDEO_C = os.environ.get("OPERIX_DEMO_VIDEO_C", "")
