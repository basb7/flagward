"""
URL configuration for the tenancy API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'organizations', views.OrganizationViewSet)
router.register(r'projects', views.ProjectViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
