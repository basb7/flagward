"""
URL configuration for the analytics API.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('overview/', views.overview, name='analytics-overview'),
    path('evaluations/timeseries/', views.evaluations_timeseries, name='analytics-evaluations-timeseries'),
    path('flags/top/', views.top_flags, name='analytics-top-flags'),
    path('sdks/health/', views.sdk_health, name='analytics-sdk-health'),
]
