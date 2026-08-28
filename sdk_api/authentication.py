"""
SDK API authentication and permissions.
"""
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from core_flags.models import Environment


class SDKAuthentication(BaseAuthentication):
    """
    Authenticate SDK requests using API key.

    Pass API key via X-API-Key header.
    """

    def authenticate(self, request):
        api_key = request.META.get("HTTP_X_API_KEY")
        if not api_key:
            # No API key - skip this auth, let other methods handle it
            return None

        try:
            environment = Environment.objects.get(api_key=api_key)
        except Environment.DoesNotExist:
            raise AuthenticationFailed(
                "Invalid API key. Check your SDK credentials."
            )

        return (environment, api_key)


class IsSDKAuthenticated(BasePermission):
    """
    Permission class that requires SDK authentication.
    """

    def has_permission(self, request, view):
        return isinstance(request.user, Environment)
