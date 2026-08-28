"""
URL configuration for SDK API.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('flags/', views.sdk_flags, name='sdk-flags'),
    path('evaluate/', views.sdk_evaluate, name='sdk-evaluate'),
    path('register/', views.sdk_register, name='sdk-register'),
    path('stream/', views.sdk_stream, name='sdk-stream'),
]
