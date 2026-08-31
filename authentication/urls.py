"""
URL configuration for authentication API.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login, name="auth-login"),
    path("register/", views.register, name="auth-register"),
    path("logout/", views.logout, name="auth-logout"),
    path("me/", views.me, name="auth-me"),
    path("refresh/", views.refresh_token, name="auth-refresh"),
    path("config/", views.auth_config, name="auth-config"),
    path("password-reset/request/", views.password_reset_request, name="auth-password-reset-request"),
    path("password-reset/confirm/", views.password_reset_confirm, name="auth-password-reset-confirm"),
]
