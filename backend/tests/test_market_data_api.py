"""Tests for market data API endpoints."""

from unittest.mock import patch
from datetime import datetime
from app.schemas.candle import CandleCreate


def _sample_candles(symbol="RELIANCE", n=5):
    return [
        CandleCreate(
            symbol=symbol,
            timeframe="1h",
            timestamp_utc=datetime(2024, 6, 1, h, 0, 0),
            open=2400.0 + h,
            high=2420.0 + h,
            low=2390.0 + h,
            close=2410.0 + h,
            volume=100000.0,
        )
        for h in range(n)
    ]


def test_fetch_market_data_success(client):
    """Fetch endpoint stores candles and returns a summary."""
    from app.utils.candle_validator import ValidationResult

    mock_candles = _sample_candles()
    mock_result = ValidationResult(valid=mock_candles, rejected=0, reasons={})

    with patch(
        "app.api.market_data.fetch_candles",
        return_value=(mock_candles, mock_result),
    ):
        response = client.get("/api/v1/market-data/fetch/RELIANCE/1h")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["fetched"] == 5
    assert data["data"]["valid"] == 5
    assert data["data"]["rejected"] == 0
    assert data["data"]["inserted"] == 5


def test_fetch_market_data_empty_response(client):
    """When yfinance returns nothing, endpoint returns success=False."""
    from app.utils.candle_validator import ValidationResult

    empty_result = ValidationResult(valid=[], rejected=0, reasons={})

    with patch(
        "app.api.market_data.fetch_candles",
        return_value=([], empty_result),
    ):
        response = client.get("/api/v1/market-data/fetch/BADTICKER/1h")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "error" in data


def test_fetch_market_data_with_rejections(client):
    """Rejected candles are counted and reported."""
    from app.utils.candle_validator import ValidationResult

    raw = _sample_candles(n=5)
    valid = raw[:4]  # one rejected
    mock_result = ValidationResult(valid=valid, rejected=1, reasons={"negative_volume": 1})

    with patch(
        "app.api.market_data.fetch_candles",
        return_value=(raw, mock_result),
    ):
        response = client.get("/api/v1/market-data/fetch/RELIANCE/1h")

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["rejected"] == 1
    assert data["data"]["valid"] == 4


def test_list_supported_symbols(client):
    response = client.get("/api/v1/market-data/symbols")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "RELIANCE" in data["data"]["symbols"]
    assert "TCS" in data["data"]["symbols"]


def test_candles_endpoint_returns_stored(client):
    """GET /candles returns what's in the DB (empty at test start)."""
    response = client.get("/api/v1/candles/RELIANCE/1h")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


def test_candles_fetch_with_sample_data(client):
    """POST /candles/fetch?use_sample=true stores synthetic data."""
    response = client.post("/api/v1/candles/RELIANCE/1h/fetch?use_sample=true")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["source"] == "sample"
    assert data["data"]["inserted"] > 0
