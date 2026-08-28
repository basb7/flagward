"""
URL configuration for the SDK monitoring API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'sdk-registrations', views.SDKRegistrationViewSet)
router.register(r'evaluations', views.EvaluationLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
