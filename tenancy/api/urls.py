"""
URL configuration for the tenancy API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'organizations', views.OrganizationViewSet)
router.register(r'organization-memberships', views.OrganizationMembershipViewSet)
router.register(r'projects', views.ProjectViewSet)
router.register(r'project-memberships', views.ProjectMembershipViewSet)
router.register(r'environment-memberships', views.EnvironmentMembershipViewSet)

urlpatterns = [
    path(
        'effective-capabilities/preview/',
        views.EffectiveCapabilitiesPreviewView.as_view(),
        name='effective-capabilities-preview',
    ),
    path('', include(router.urls)),
]
