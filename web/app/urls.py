from django.urls import path
from . import views
from django.views.generic import TemplateView
urlpatterns = [
    path('', views.home, name='home'),
    path('checkout/', views.checkout, name='checkout'),
    path('cart/', views.cart, name='cart'),
    path('loginn/', views.loginn, name= "loginn"),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name="register"),
    path('product/', views.product, name='product'),
    path('detail/<slug:slug>', views.detail, name='detail' ),
    path('search', views.search, name='search'),
    path('add-to-cart/<slug:slug>', views.add_to_cart, name="add_to_cart" ),
    path('resert_password/', views.password_reset, name="reset_password"),
    path('resert_password_sent/', TemplateView.as_view(template_name="password_reset_done.html"), name="password_reset_done"),
    path('resert/<uidb64>/<token>/', views.password_reset_confirm, name="password_reset_confirm"),
    path('resert_password_complete/', TemplateView.as_view(template_name="password_reset_complete.html"), name="password_reset_complete"),
    path("arrow_up/<slug:slug>", views.arrow_up, name='arrow_up' ),
    path("arrow_down/<slug:slug>", views.arrow_down, name='arrow_down' ),
    path("productPage/", views.productPage, name="productPage"),
    path('promotions/', views.promotion_list, name='promotion_list'),
    path('promotions/use/<int:promo_id>/', views.use_promotion, name='use_promotion'),
    path('promotions/cancel/<int:promo_id>/', views.cancel_promotion, name='cancel_promotion'),
    path('add-to-cart-detail/<slug:slug>', views.add_to_cart_detail, name="add_to_cart_detail" ),
    path('product/<slug:slug>/add_review/', views.add_review, name='add_review'),
    path('review/<int:review_id>/reply/', views.reply_review, name='reply_review'),
    path('profile/', views.profile_view, name='profile'),
    path("complete/", views.complete_cart, name = "complete"),
    path("policy/", views.policy, name="policy")


]
