"""
URL configuration for flagward project.
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    """Health check endpoint for monitoring."""
    return JsonResponse({"status": "healthy"})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', health_check),
    path('api/v1/auth/', include('authentication.urls')),
    path('api/v1/', include('core_flags.api.urls')),
    path('api/v1/', include('sdk_api.api.urls')),
    path('api/v1/tenancy/', include('tenancy.api.urls')),
    path('api/v1/analytics/', include('analytics.api.urls')),
    path('api/v1/sdk/', include('sdk_api.urls')),
]
