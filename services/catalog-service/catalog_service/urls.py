from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from greenmart_common.health import make_health_view
from greenmart_common.observability import observability_urls

urlpatterns = [
    path("health/", make_health_view("catalog-service")),
    path("admin/catalog/", admin.site.urls),
    path("api/", include("catalog.urls")),
]
# Phục vụ ảnh sản phẩm. Docker Compose: nginx đọc thẳng volume nên không chạm tới route này;
# Kubernetes không có EFS: gateway proxy /media/ về đây (lưu lượng ảnh nhỏ, đủ dùng cho quy mô hiện tại).
urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

# /metrics cho Prometheus (chỉ khi ENABLE_PROMETHEUS=1); đặt đầu danh sách để không bị route khác nuốt.
urlpatterns = observability_urls() + urlpatterns
