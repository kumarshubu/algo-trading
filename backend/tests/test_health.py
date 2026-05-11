"""Tests for health check endpoint."""


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "ok"
    assert data["data"]["paper_trading"] is True
