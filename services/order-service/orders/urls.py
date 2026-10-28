from django.urls import path

from . import views

urlpatterns = [
    path("carts/current/", views.CurrentCartView.as_view()),
    path("carts/current/items/", views.CartItemView.as_view()),
    path("carts/current/promotion/", views.ApplyPromotionView.as_view()),
    path("carts/current/promotion/clear/", views.ClearPromotionView.as_view()),
    path("carts/merge/", views.MergeCartView.as_view()),
    path("orders/", views.OrderListView.as_view()),
    path("orders/complete/", views.CompleteOrderView.as_view()),
    path("orders/stats/", views.StatsView.as_view()),
]
