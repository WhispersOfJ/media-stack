import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("CONTROL_PANEL_DEBUG", "") == "1"

_secret_key_env = os.environ.get("CONTROL_PANEL_SECRET_KEY")
if not _secret_key_env and not DEBUG:
    raise RuntimeError(
        "CONTROL_PANEL_SECRET_KEY must be set - see docker-compose.yml's control-panel environment block"
    )
SECRET_KEY = _secret_key_env or "dev-only-insecure-key-do-not-deploy"

ALLOWED_HOSTS = ["*"]  # narrowed by core.middleware.VerifySameOriginMiddleware, not Django's own check

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "auth_app",
    "ratings",
    "seerr",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.VerifySameOriginMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
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
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("CONTROL_PANEL_DB_PATH", str(BASE_DIR / "dev-control-panel.db")),
    }
}

# django.contrib.auth's own User model (auth_user table, brand new — does not
# collide with the preserved `users` table) backs ONLY /admin/ logins via
# `manage.py createsuperuser`. The real control-panel login (auth_app) uses
# core.models.User against the preserved `users` table and never touches
# django.contrib.auth's session/user machinery — see core/authentication.py.

SESSION_COOKIE_NAME = "cp_session"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days, matches the retired itsdangerous SESSION_MAX_AGE
SESSION_ENGINE = "django.contrib.sessions.backends.db"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["core.authentication.SessionOrApiKeyAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["core.permissions.IsAuthenticatedOrServiceKey"],
    "EXCEPTION_HANDLER": "core.api_base.envelope_exception_handler",
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

LOGIN_URL = "auth_app:login"

STATIC_URL = "static/"
