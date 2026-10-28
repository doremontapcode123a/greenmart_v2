from django.urls import include, path

from greenmart_common.health import make_health_view

urlpatterns = [
    path("health/", make_health_view("promotion-service")),
    path("api/", include("promotions.urls")),
]
