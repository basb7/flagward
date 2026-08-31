"""
Authentication API endpoints with httpOnly cookies.
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.emails import normalize_email, validate_normalized_email
from tenancy.capabilities import resolve_capabilities
from tenancy.models import OrganizationMembership
from tenancy.permissions import IsDashboardUser


def set_tokens_cookies(response, refresh_token, access_token):
    """Set httpOnly cookies for tokens."""
    # Access token cookie
    response.set_cookie(
        settings.SIMPLE_JWT['AUTH_COOKIE'],
        access_token,
        max_age=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
        httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
        samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
        path='/',
    )

    # Refresh token cookie
    response.set_cookie(
        settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
        refresh_token,
        max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
        httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
        samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
        path='/',
    )

    return response


def delete_tokens_cookies(response):
    """Delete token cookies."""
    response.delete_cookie(
        settings.SIMPLE_JWT['AUTH_COOKIE'],
        path='/',
    )
    response.delete_cookie(
        settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
        path='/',
    )
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """
    Login endpoint - sets httpOnly cookies.

    POST body:
    {
        "username": "admin",
        "password": "admin123"
    }
    """
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response(
            {"error": "Username and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Authenticate user
    user = authenticate(username=username, password=password)

    if user is None:
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # Generate tokens
    refresh = RefreshToken.for_user(user)

    # Create response with user data
    response = Response(
        {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
        },
        status=status.HTTP_200_OK,
    )

    # Set httpOnly cookies
    set_tokens_cookies(response, str(refresh), str(refresh.access_token))

    return response


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """
    Register endpoint - sets httpOnly cookies.

    POST body:
    {
        "username": "newuser",
        "email": "user@example.com",
        "password": "password123"
    }
    """
    username = request.data.get("username")
    email = request.data.get("email")
    password = request.data.get("password")

    if not username or not password or not email:
        return Response(
            {"error": "Username, email, and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if user exists
    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already exists"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Email is a required, unique identity (step 1 of password reset: a
    # reset proves control of a channel the account owns). Normalise the
    # same way authentication/migrations/0001_email_required_unique.py
    # normalises existing rows, so this check and the database's unique
    # index always agree on what "the same address" means.
    email = normalize_email(email)
    try:
        validate_normalized_email(email)
    except DjangoValidationError:
        return Response(
            {"email": ["Enter a valid email address."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(email=email).exists():
        return Response(
            {"email": ["Email already exists"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # AUTH_PASSWORD_VALIDATORS (settings.py) is configured but does nothing on
    # its own: Django only applies it where `validate_password` is called, and
    # this endpoint never called it. Registration accepted a one-character
    # password, and member creation checked length and nothing else, so
    # "12345678" passed both the common-password and numeric-only validators
    # the project had already decided it wanted.
    try:
        validate_password(password, user=User(username=username, email=email or ""))
    except DjangoValidationError as exc:
        return Response({"password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

    # Registration creates the user only (spec/organization-management:
    # Self-Registration Creates Only the User). The first organization is
    # created explicitly from the dashboard's empty state, which is what lets
    # the person name it themselves instead of inheriting a generated name.
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
    )

    # Generate tokens
    refresh = RefreshToken.for_user(user)

    # Create response with user data
    response = Response(
        {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
        },
        status=status.HTTP_201_CREATED,
    )

    # Set httpOnly cookies
    set_tokens_cookies(response, str(refresh), str(refresh.access_token))

    return response


@api_view(["POST"])
@permission_classes([IsDashboardUser])
def logout(request):
    """
    Logout endpoint - clears cookies.
    """
    response = Response(
        {"message": "Successfully logged out"},
        status=status.HTTP_200_OK,
    )

    # Delete token cookies
    delete_tokens_cookies(response)

    return response


@api_view(["GET"])
@permission_classes([IsDashboardUser])
def me(request):
    """
    Get current user info, plus the caller's resolved capabilities per
    organization it belongs to.

    Capabilities are answered through `resolve_capabilities` -- the same pure
    function `tenancy.scoping.capabilities_for` calls for real enforcement --
    so this can never drift into a second source of truth. Granularity is
    per-organization: no project or environment role is folded in, because
    the only capability the dashboard needs at this level (`project.create`)
    is exclusively an organization-role grant (see `tenancy/capabilities.py`).
    """
    user = request.user
    memberships = OrganizationMembership.objects.filter(user=user).values(
        "organization_id", "role"
    )
    organizations = [
        {
            "id": str(membership["organization_id"]),
            "capabilities": sorted(resolve_capabilities(membership["role"], None, None)),
        }
        for membership in memberships
    ]
    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "organizations": organizations,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_token(request):
    """
    Refresh access token using refresh cookie.

    The refresh token is automatically sent in the cookie.
    """
    refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])

    if not refresh_token:
        return Response(
            {"error": "Refresh token not found in cookies"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        refresh = RefreshToken(refresh_token)
        new_access_token = str(refresh.access_token)

        # Create response
        response = Response(
            {"message": "Token refreshed"},
            status=status.HTTP_200_OK,
        )

        # Set new access token cookie
        response.set_cookie(
            settings.SIMPLE_JWT['AUTH_COOKIE'],
            new_access_token,
            max_age=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
            httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
            path='/',
        )

        # If rotate refresh tokens, also set new refresh token.
        # Re-serialising the incoming token would return the same string with
        # the same expiry, so the deadline has to be moved explicitly: without
        # this, a session dies REFRESH_TOKEN_LIFETIME after login no matter how
        # actively it is used.
        if settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS'):
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            new_refresh_token = str(refresh)
            response.set_cookie(
                settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
                new_refresh_token,
                max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
                httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
                path='/',
            )

        return response

    except Exception:
        return Response(
            {"error": "Invalid refresh token"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
