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
router.register(r'invitations', views.InvitationViewSet)

urlpatterns = [
    path(
        'effective-capabilities/preview/',
        views.EffectiveCapabilitiesPreviewView.as_view(),
        name='effective-capabilities-preview',
    ),
    # Token-addressed, not pk-addressed -- distinct trailing literal
    # ('preview'/'accept') from the router's own `invitations/{pk}/revoke/`,
    # so there is no path collision either way these are ordered.
    path(
        'invitations/<str:token>/preview/',
        views.InvitationPreviewView.as_view(),
        name='invitation-preview',
    ),
    path(
        'invitations/<str:token>/accept/',
        views.InvitationAcceptView.as_view(),
        name='invitation-accept',
    ),
    path('', include(router.urls)),
]
