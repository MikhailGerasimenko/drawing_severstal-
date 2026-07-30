from pathlib import Path

import pytest


@pytest.mark.unit
def test_convert_returns_base_response(client, tmp_path):
    samples = Path(__file__).resolve().parents[1] / "samples"
    dxf = next(samples.glob("*.dxf"), None)
    if dxf is None:
        pytest.skip("no sample dxf")

    with dxf.open("rb") as handle:
        response = client.post(
            "/api/v1/convert",
            files={"file": (dxf.name, handle, "application/octet-stream")},
            data={"render_png": "false", "name": "test_drawing"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "request_id" in body
    assert "timestamp" in body
    data = body["data"]
    assert data["source_file"] == dxf.name
    assert data["llm_context"]
    assert "json" in data["files"]
    assert data["validation_gate"]["status"] in {"pass", "warn", "fail", "unknown"}
    assert "X-Request-ID" in response.headers


@pytest.mark.unit
def test_convert_rejects_non_dxf(client):
    response = client.post(
        "/api/v1/convert",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422
    body = response.json()
    assert "error" in body
