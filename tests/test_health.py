import pytest


@pytest.mark.unit
def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert "DXF Converter" in payload["message"]
    assert payload["docs"] == "/docs"
    assert "version" in payload


@pytest.mark.unit
def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "DXF Converter"
    assert "timestamp" in payload
