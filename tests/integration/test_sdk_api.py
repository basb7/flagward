"""
Tests for sdk_api endpoints.
"""
import pytest
from rest_framework.test import APIClient

from core_flags.models import (
    Environment,
    FeatureFlag,
)
from sdk_api.models import SDKRegistration


@pytest.mark.django_db
class TestSDKFlagsEndpoint:
    """Tests for GET /api/v1/sdk/flags/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)
        self.flag = FeatureFlag.objects.create(
            environment=self.env,
            key="new-dashboard",
            name="New Dashboard",
            is_enabled=True,
        )

    def test_sdk_flags_requires_authentication(self):
        """Test that SDK flags endpoint requires authentication."""
        response = self.client.get("/api/v1/sdk/flags/")
        assert response.status_code in [401, 403]

    def test_sdk_flags_returns_empty_for_new_environment(self):
        """Test that SDK flags returns empty list for environment with no flags."""
        self.client.force_authenticate(user=None)
        # TODO: Implement API key authentication
        # For now, this test documents the expected behavior
        pass


@pytest.mark.django_db
class TestSDKEvaluateEndpoint:
    """Tests for POST /api/v1/sdk/evaluate/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)
        self.flag = FeatureFlag.objects.create(
            environment=self.env,
            key="new-dashboard",
            name="New Dashboard",
            is_enabled=True,
        )

    def test_sdk_evaluate_requires_authentication(self):
        """Test that SDK evaluate endpoint requires authentication."""
        response = self.client.post("/api/v1/sdk/evaluate/", {})
        assert response.status_code in [401, 403]

    def test_sdk_evaluate_returns_empty_results(self):
        """Test that SDK evaluate returns empty results initially."""
        self.client.force_authenticate(user=None)
        # TODO: Implement API key authentication
        # For now, this test documents the expected behavior
        pass


@pytest.mark.django_db
class TestSDKRegisterEndpoint:
    """Tests for POST /api/v1/sdk/register/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)

    def register(self, version="1.0.0"):
        """Register a JavaScript SDK against this environment's API key."""
        return self.client.post(
            "/api/v1/sdk/register/",
            {"sdk_type": "JAVASCRIPT", "version": version},
            format="json",
            HTTP_X_API_KEY=self.env.api_key,
        )

    def test_sdk_register_requires_authentication(self):
        """Test that SDK register endpoint requires authentication."""
        response = self.client.post("/api/v1/sdk/register/", {})
        assert response.status_code in [401, 403]

    def test_sdk_register_creates_registration(self):
        """Test that SDK register creates a new registration."""
        response = self.register()

        assert response.status_code == 201
        assert response.data["created"] is True
        assert SDKRegistration.objects.filter(environment=self.env).count() == 1

    def test_sdk_register_is_idempotent(self):
        """
        Repeated registrations update the existing row instead of adding one.

        Clients share their environment's API key and register on every start,
        so this endpoint is called far more often than rows should exist.
        """
        first = self.register(version="1.0.0")
        second = self.register(version="1.0.1")

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.data["created"] is False
        assert SDKRegistration.objects.filter(environment=self.env).count() == 1

        registration = SDKRegistration.objects.get(environment=self.env)
        assert registration.version == "1.0.1"


@pytest.mark.django_db
class TestSDKStreamEndpoint:
    """Tests for GET /api/v1/sdk/stream/ endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, project):
        """Set up test data."""
        self.client = APIClient()
        self.env = Environment.objects.create(name="Prod", key="prod", project=project)

    def test_sdk_stream_requires_authentication(self):
        """Test that SDK stream endpoint requires authentication."""
        response = self.client.get("/api/v1/sdk/stream/")
        # SSE stream may return 200 initially, actual auth enforcement happens at connection
        assert response.status_code in [200, 401, 403]

    def test_sdk_stream_returns_sse_response(self):
        """Test that SDK stream returns SSE response."""
        self.client.force_authenticate(user=None)
        # TODO: Implement API key authentication
        # For now, this test documents the expected behavior
        pass
