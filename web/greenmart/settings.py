"""web (BFF): giao diện storefront + admin panel. Không chứa dữ liệu nghiệp vụ; gọi các service qua HTTP.
Database web_db chỉ dùng cho session."""
import os
from pathlib import Path

from greenmart_common.env import env, env_bool, env_list, mysql_database

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env("SECRET_KEY", required=True)
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*")
INTERNAL_API_TOKEN = env("INTERNAL_API_TOKEN", required=True)

USER_SERVICE_URL = env("USER_SERVICE_URL", "http://user-service:8000")
CATALOG_SERVICE_URL = env("CATALOG_SERVICE_URL", "http://catalog-service:8000")
ORDER_SERVICE_URL = env("ORDER_SERVICE_URL", "http://order-service:8000")
PROMOTION_SERVICE_URL = env("PROMOTION_SERVICE_URL", "http://promotion-service:8000")

INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "app",
    "adminpanel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "greenmart.middleware.RemoteUserMiddleware",   # request.user lấy từ user-service
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "greenmart.middleware.ServiceErrorMiddleware",  # service phụ thuộc chết -> trang 503 thân thiện
]

ROOT_URLCONF = "greenmart.urls"
WSGI_APPLICATION = "greenmart.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.messages.context_processors.messages",
        "greenmart.context.user",
    ]},
}]

DATABASES = {"default": mysql_database("DB")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_ENGINE = "django.contrib.sessions.backends.db"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", "/staticfiles")

LOGIN_URL = "/loginn/"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:8088,http://127.0.0.1:8088")
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
