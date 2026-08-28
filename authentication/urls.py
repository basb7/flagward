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
]
