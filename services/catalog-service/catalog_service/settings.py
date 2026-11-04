"""catalog-service: danh mục, sản phẩm, đánh giá. Database riêng: catalog_db (MySQL)."""
from pathlib import Path

from greenmart_common.env import env, env_bool, env_list, mysql_database

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env("SECRET_KEY", required=True)
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*")
INTERNAL_API_TOKEN = env("INTERNAL_API_TOKEN", required=True)

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "catalog_service.urls"
WSGI_APPLICATION = "catalog_service.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {"default": mysql_database("DB")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", "/staticfiles")
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", "/media")
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Django admin của catalog-service được gateway publish tại /admin/catalog/.
SESSION_COOKIE_NAME = "gm_catalog_admin_sessionid"
CSRF_COOKIE_NAME = "gm_catalog_admin_csrftoken"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:8088,http://127.0.0.1:8088")
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PERMISSION_CLASSES": ["greenmart_common.internal_auth.IsInternalService"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

JAZZMIN_SETTINGS = {"site_title": "GreenMart – Catalog", "site_header": "GreenMart Catalog", "welcome_sign": "GreenMart – quản trị danh mục & sản phẩm"}

# Quan sát: Prometheus /metrics + AWS X-Ray (bật bằng ENABLE_PROMETHEUS / ENABLE_XRAY, mặc định tắt).
from greenmart_common.observability import apply as _apply_observability  # noqa: E402

_apply_observability(globals(), "catalog-service")
