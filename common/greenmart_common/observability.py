"""Quan sát (observability): Prometheus (django-prometheus) và AWS X-Ray, bật bằng biến môi trường.

  ENABLE_PROMETHEUS=1   thêm endpoint /metrics (số request, độ trễ, mã trạng thái theo view)
  ENABLE_XRAY=1         gửi trace tới X-Ray daemon (XRAY_DAEMON_ADDRESS, mặc định xray-daemon.monitoring:2000)

Mặc định cả hai TẮT nên chạy local / docker compose như cũ. Gọi ở cuối settings.py của mỗi service:
    from greenmart_common.observability import apply
    apply(globals(), "user-service")
và trong urls.py:
    urlpatterns = observability_urls() + urlpatterns
"""
import os

from django.urls import include, path

from .env import env, env_bool


def prometheus_enabled():
    return env_bool("ENABLE_PROMETHEUS", False)


def xray_enabled():
    return env_bool("ENABLE_XRAY", False)


def apply(settings, service_name):
    """Chèn app/middleware quan sát vào settings của service (dict `globals()` của settings.py)."""
    apps = list(settings["INSTALLED_APPS"])
    middleware = list(settings["MIDDLEWARE"])

    if prometheus_enabled():
        # Chế độ nhiều worker: thư mục chung phải tồn tại trước khi tạo metric đầu tiên (kể cả khi chạy manage.py).
        if multiprocess_dir():
            os.makedirs(multiprocess_dir(), exist_ok=True)
        apps.append("django_prometheus")
        middleware = (
            ["django_prometheus.middleware.PrometheusBeforeMiddleware"]
            + middleware
            + ["django_prometheus.middleware.PrometheusAfterMiddleware"]
        )

    if xray_enabled():
        apps.append("aws_xray_sdk.ext.django")
        middleware = ["aws_xray_sdk.ext.django.middleware.XRayMiddleware"] + middleware
        settings["XRAY_RECORDER"] = {
            "AWS_XRAY_DAEMON_ADDRESS": env("XRAY_DAEMON_ADDRESS", "xray-daemon.monitoring:2000"),
            "AWS_XRAY_TRACING_NAME": f"greenmart-{service_name}",
            # Request đi ra ngoài mà không nằm trong trace (vd. lệnh manage.py) chỉ ghi log, không làm lỗi.
            "AWS_XRAY_CONTEXT_MISSING": "LOG_ERROR",
            "AUTO_INSTRUMENT": env_bool("XRAY_AUTO_INSTRUMENT", False),
            # Luật lấy mẫu chính nằm ở X-Ray (Terraform: aws_xray_sampling_rule); đây là luật dự phòng khi daemon chưa sẵn sàng.
            "SAMPLING": True,
            "SAMPLING_RULES": {
                "version": 2,
                "rules": [
                    {"description": "bo qua health/metrics", "host": "*", "http_method": "*",
                     "url_path": "/health*", "fixed_target": 0, "rate": 0.0},
                    {"description": "bo qua metrics", "host": "*", "http_method": "*",
                     "url_path": "/metrics*", "fixed_target": 0, "rate": 0.0},
                ],
                "default": {"fixed_target": 1, "rate": float(env("XRAY_SAMPLE_RATE", "1.0"))},
            },
        }
        # Gắn header trace vào các lời gọi service-to-service (greenmart_common.client dùng `requests`).
        from aws_xray_sdk.core import patch

        patch(("requests",))

    settings["INSTALLED_APPS"] = apps
    settings["MIDDLEWARE"] = middleware


def observability_urls():
    """URL /metrics (chỉ khi bật Prometheus). Gateway chặn /metrics ra Internet; Prometheus scrape thẳng vào pod."""
    if not prometheus_enabled():
        return []
    return [path("", include("django_prometheus.urls"))]


def multiprocess_dir():
    return os.environ.get("PROMETHEUS_MULTIPROC_DIR", "")
