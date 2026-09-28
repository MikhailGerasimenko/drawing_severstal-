from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def clear_api_token(monkeypatch):
    """Отключаем внутренний токен в тестах для backward compatibility."""
    monkeypatch.setattr(settings, "api_token", "")


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)
