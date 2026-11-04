from django.urls import include, path

from greenmart_common.health import make_health_view
from greenmart_common.observability import observability_urls

urlpatterns = [
    path("health/", make_health_view("promotion-service")),
    path("api/", include("promotions.urls")),
]

# /metrics cho Prometheus (chỉ khi ENABLE_PROMETHEUS=1); đặt đầu danh sách để không bị route khác nuốt.
urlpatterns = observability_urls() + urlpatterns
