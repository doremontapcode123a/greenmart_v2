from django.urls import include, path

from greenmart_common.health import make_health_view

urlpatterns = [
    path("healthz/", make_health_view("web")),
    path("", include("app.urls")),
    path("admin_panel/", include("adminpanel.urls")),
    # /admin/ (Django admin) và /admin/catalog/ do gateway chuyển thẳng tới user-service / catalog-service.
]
