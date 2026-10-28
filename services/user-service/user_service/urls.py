from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from greenmart_common.health import make_health_view

urlpatterns = [
    path("health/", make_health_view("user-service")),
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    # Tên 'password_reset_confirm' cần tồn tại để template email của Django dựng được link.
    # Link thật trỏ tới trang của web (BFF): /resert/<uid>/<token>/ (cùng đường dẫn).
    path("resert/<uidb64>/<token>/", lambda request, uidb64, token: HttpResponse(status=404), name="password_reset_confirm"),
]
