from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from greenmart_common.health import make_health_view

urlpatterns = [
    path("health/", make_health_view("catalog-service")),
    path("admin/catalog/", admin.site.urls),
    path("api/", include("catalog.urls")),
]
# Chỉ để tiện khi chạy dev không qua gateway; ở môi trường compose nginx phục vụ /media/.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
