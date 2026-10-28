from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.CategoryListView.as_view()),
    path("products/", views.ProductListCreateView.as_view()),
    path("products/<slug:slug>/", views.ProductDetailView.as_view()),
    path("products/<slug:slug>/hide/", views.ProductHideView.as_view()),
    path("products/<slug:slug>/reviews/", views.ProductReviewCreateView.as_view()),
    path("reviews/<int:review_id>/reply/", views.ReviewReplyView.as_view()),
    path("stats/", views.StatsView.as_view()),
]
