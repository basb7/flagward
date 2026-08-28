"""
URL configuration for core_flags API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'environments', views.EnvironmentViewSet)
router.register(r'flags', views.FeatureFlagViewSet)
router.register(r'rules', views.StrategyRuleViewSet)
router.register(r'conditions', views.ConditionViewSet)
router.register(r'overrides', views.FlagOverrideViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
