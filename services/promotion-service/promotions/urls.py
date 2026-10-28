from django.urls import path

from . import views

urlpatterns = [
    path("promotions/", views.PromotionListCreateView.as_view()),
    path("promotions/<int:promo_id>/", views.PromotionDetailView.as_view()),
]
