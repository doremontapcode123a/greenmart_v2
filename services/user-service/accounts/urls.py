from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.LoginView.as_view()),
    path("users/register/", views.RegisterView.as_view()),
    path("users/", views.UserListView.as_view()),
    path("users/stats/", views.StatsView.as_view()),
    path("users/<int:user_id>/", views.UserDetailView.as_view()),
    path("users/<int:user_id>/toggle-active/", views.UserToggleActiveView.as_view()),
    path("users/<int:user_id>/profile/", views.ProfileView.as_view()),
    path("password-reset/request/", views.PasswordResetRequestView.as_view()),
    path("password-reset/validate/", views.PasswordResetValidateView.as_view()),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
]
