"""Đọc cấu hình từ biến môi trường (12-factor)."""
import os


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Thiếu biến môi trường bắt buộc: {name}")
    return value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def mysql_database(prefix="DB"):
    """Cấu hình DATABASES['default'] cho MySQL từ biến DB_* (utf8mb4, strict mode)."""
    return {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env(f"{prefix}_NAME", required=True),
        "USER": env(f"{prefix}_USER", required=True),
        "PASSWORD": env(f"{prefix}_PASSWORD", required=True),
        "HOST": env(f"{prefix}_HOST", "mysql"),
        "PORT": env(f"{prefix}_PORT", "3306"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
