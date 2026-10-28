from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_login, name='admin_login'),                    
    path('dashboard/', views.dashboard, name='admin_dashboard'),        
    path('products/', views.product_list, name='admin_products'),         
    path('orders/', views.order_list, name='admin_orders'),             
    path('users/', views.user_list, name='admin_users'),                 
    path('users/toggle/<int:user_id>/', views.toggle_user_status, name='admin_user_toggle'),
    path("logout", views.logout_view, name='logout'),
    path("addProduct/", views.add_product, name="add_product"),
    path("editProduct/<slug:slug>", views.edit_product, name="edit_product"),
    path("deleteProduct/<slug:slug>", views.delete_product, name="delete_product"),
    path("admin_promotion", views.promotion,name='admin_promotion'),
    path("addPromotion", views.add_promotion, name="add_promotion"),
    path("deletePromotion/<int:id>", views.delete_promotion, name="delete_promotion"),
    path("editPrommotion/<int:id>",views.edit_promotion, name="edit_promotion" ),
    path("orders_complete/", views.orders_complete, name="orders_complete")
]