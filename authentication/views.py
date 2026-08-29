"""
Authentication API endpoints with httpOnly cookies.
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from tenancy.models import Organization, OrganizationMembership, OrganizationRole
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

    if not username or not password:
        return Response(
            {"error": "Username and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if user exists
    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already exists"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create the user and auto-provision an organization the user administers
    # (spec/organization-management: Self-Registration Auto-Provisions an
    # Organization). One transaction: a user must never exist without the
    # organization membership that makes it navigable.
    with transaction.atomic():
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        organization = Organization.objects.create(name=f"{username}'s Organization")
        OrganizationMembership.objects.create(
            organization=organization, user=user, role=OrganizationRole.ADMIN
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
    Get current user info.
    """
    user = request.user
    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
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
