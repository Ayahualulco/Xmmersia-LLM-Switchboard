"""
Tests for REST API
══════════════════
"""

import pytest
from fastapi.testclient import TestClient

from llm_switchboard import Switchboard
from llm_switchboard.api.routes import create_app
from llm_switchboard.core.health_engine import StatusPageSignal


@pytest.fixture
def client():
    """Create a test client with a configured Switchboard."""
    sb = Switchboard()
    # Seed with some health data
    sb.update_status(
        "anthropic",
        StatusPageSignal(provider="anthropic", status="operational"),
    )
    sb.update_status(
        "openai",
        StatusPageSignal(provider="openai", status="operational"),
    )
    app = create_app(switchboard=sb)
    return TestClient(app)


class TestHealthEndpoints:
    def test_check_model(self, client):
        response = client.get("/health/claude-opus-4-6")
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "claude-opus-4-6"
        assert data["status"] == "healthy"

    def test_check_all(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "claude-opus-4-6" in data

    def test_check_unknown_model(self, client):
        response = client.get("/health/nonexistent-model")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unknown"


class TestRouteEndpoint:
    def test_basic_route(self, client):
        response = client.post("/route", json={
            "preferred_model": "claude-opus-4-6",
            "policy": "careful",
        })
        assert response.status_code == 200
        data = response.json()
        assert "routed_to" in data
        assert "action" in data
        assert "provenance" in data


class TestProviderEndpoints:
    def test_list_providers(self, client):
        response = client.get("/providers")
        assert response.status_code == 200
        data = response.json()
        assert "anthropic" in data["providers"]

    def test_list_provider_models(self, client):
        response = client.get("/providers/anthropic/models")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "anthropic"
        assert len(data["models"]) > 0

    def test_unknown_provider(self, client):
        response = client.get("/providers/nonexistent/models")
        assert response.status_code == 404


class TestStatusEndpoint:
    def test_status(self, client):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["switchboard_version"] == "1.0.1"
        assert "health_summary" in data


class TestStampEndpoint:
    def test_stamp_not_found(self, client):
        response = client.get("/stamp/nonexistent")
        assert response.status_code == 404
