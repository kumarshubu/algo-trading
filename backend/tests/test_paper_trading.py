"""
Tests for paper trading engine.
PAPER TRADING ONLY - NO REAL EXECUTION.
"""

import pytest
from app.services.paper_trading import (
    get_or_create_portfolio,
    simulate_order,
    simulate_close_position,
    simulate_pnl,
)
from app.schemas.trade import SimulateOrderRequest
from app.core.exceptions import InsufficientBalanceError

# Keep price * quantity well under 10% of ₹100,000 (= ₹10,000 max per trade)
_BUY_RELIANCE = SimulateOrderRequest(
    symbol="RELIANCE", side="BUY", quantity=10, price=500.0, strategy_name="ema_rsi_volume"
)
_BUY_TCS = SimulateOrderRequest(
    symbol="TCS", side="BUY", quantity=5, price=600.0, strategy_name="ema_rsi_volume"
)
_BUY_INFY = SimulateOrderRequest(
    symbol="INFY", side="BUY", quantity=10, price=500.0, strategy_name="ema_rsi_volume"
)


def test_portfolio_initialized(db):
    portfolio = get_or_create_portfolio(db)
    assert portfolio.virtual_balance == 100000.0
    assert portfolio.initial_balance == 100000.0
    assert portfolio.total_realized_pnl == 0.0


def test_simulate_buy_order(db):
    trade = simulate_order(db, _BUY_RELIANCE)
    assert trade.symbol == "RELIANCE"
    assert trade.side == "BUY"
    assert trade.status == "OPEN"
    assert trade.entry_price > 500.0  # slippage applied


def test_simulate_close_position(db):
    simulate_order(db, _BUY_TCS)
    trade = simulate_close_position(db, "TCS", current_price=700.0)
    assert trade is not None
    assert trade.status == "CLOSED"
    assert trade.exit_price is not None
    assert trade.pnl is not None


def test_simulate_pnl_buy():
    pnl = simulate_pnl(entry_price=1000.0, current_price=1100.0, quantity=10, side="BUY")
    assert pnl == pytest.approx(1000.0)


def test_simulate_pnl_loss():
    pnl = simulate_pnl(entry_price=1000.0, current_price=950.0, quantity=10, side="BUY")
    assert pnl == pytest.approx(-500.0)


def test_balance_reduced_after_buy(db):
    portfolio = get_or_create_portfolio(db)
    initial = portfolio.virtual_balance

    simulate_order(db, _BUY_INFY)

    db.refresh(portfolio)
    assert portfolio.virtual_balance < initial


def test_reset_portfolio(client):
    response = client.post("/api/v1/trading/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["balance"] == 100000.0
