"""promotion-service: khuyến mãi. Database riêng: promotion_db (MySQL). Không expose ra ngoài gateway."""
from pathlib import Path

from greenmart_common.env import env, env_bool, env_list, mysql_database

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env("SECRET_KEY", required=True)
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*")
INTERNAL_API_TOKEN = env("INTERNAL_API_TOKEN", required=True)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "promotions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "promotion_service.urls"
WSGI_APPLICATION = "promotion_service.wsgi.application"

DATABASES = {"default": mysql_database("DB")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PERMISSION_CLASSES": ["greenmart_common.internal_auth.IsInternalService"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# Quan sát: Prometheus /metrics + AWS X-Ray (bật bằng ENABLE_PROMETHEUS / ENABLE_XRAY, mặc định tắt).
from greenmart_common.observability import apply as _apply_observability  # noqa: E402

_apply_observability(globals(), "promotion-service")
