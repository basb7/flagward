"""
JWT Authentication with cookie support.
"""
from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthenticationCookie(JWTAuthentication):
    """
    JWT Authentication that reads tokens from httpOnly cookies.
    """

    def authenticate(self, request):
        # Try to get token from cookie first
        access_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])

        if access_token:
            # Validate the token
            try:
                validated_token = self.get_validated_token(access_token)
                user = self.get_user(validated_token)
                return (user, validated_token)
            except Exception:
                pass

        # Fall back to header authentication
        return super().authenticate(request)
