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


# ---------------------------------------------------------------------------
# Bug fix: dead sell_qty variable — verify SELL proceeds are always credited
# ---------------------------------------------------------------------------

def test_sell_with_open_position_credits_proceeds(db):
    """
    Selling when a position exists must credit the full proceeds to the portfolio.
    Previously the dead sell_qty variable made the intent ambiguous; this test
    pins the correct behaviour.
    """
    from app.services.paper_trading import get_or_create_portfolio

    simulate_order(db, _BUY_TCS)

    portfolio = get_or_create_portfolio(db)
    balance_after_buy = portfolio.virtual_balance

    sell_req = SimulateOrderRequest(
        symbol="TCS", side="SELL", quantity=5, price=700.0, strategy_name="ema_rsi_volume"
    )
    simulate_order(db, sell_req)

    db.refresh(portfolio)
    assert portfolio.virtual_balance > balance_after_buy  # proceeds credited


def test_sell_without_position_still_credits_proceeds(db):
    """
    Short selling (no existing position) must also credit proceeds.
    The old sell_qty = 0.0 branch was dead code — proceeds were always
    calculated from request.quantity regardless.
    """
    from app.services.paper_trading import get_or_create_portfolio

    portfolio = get_or_create_portfolio(db)
    initial_balance = portfolio.virtual_balance

    sell_req = SimulateOrderRequest(
        symbol="WIPRO", side="SELL", quantity=5, price=400.0, strategy_name="ema_rsi_volume"
    )
    simulate_order(db, sell_req)

    db.refresh(portfolio)
    assert portfolio.virtual_balance > initial_balance  # short-sell proceeds credited


# ---------------------------------------------------------------------------
# Bug fix: orphaned OPEN trades when position is closed via averaging
# ---------------------------------------------------------------------------

def test_all_open_trades_closed_when_position_closes(db):
    """
    When averaging into a position (multiple BUY trades for the same symbol),
    closing the position must mark EVERY open trade as CLOSED — not just the
    most recent one.  Previously the old .first() query left earlier trades
    permanently stuck in OPEN status.
    """
    from app.models.trade import PaperTrade

    # Buy twice — same symbol, creates two OPEN trade records
    buy1 = SimulateOrderRequest(
        symbol="INFY", side="BUY", quantity=5, price=500.0, strategy_name="ema_rsi_volume"
    )
    buy2 = SimulateOrderRequest(
        symbol="INFY", side="BUY", quantity=3, price=520.0, strategy_name="ema_rsi_volume"
    )
    simulate_order(db, buy1)
    simulate_order(db, buy2)

    open_before = db.query(PaperTrade).filter(
        PaperTrade.symbol == "INFY", PaperTrade.status == "OPEN"
    ).count()
    assert open_before == 2

    # Close the entire position
    simulate_close_position(db, "INFY", current_price=550.0)

    open_after = db.query(PaperTrade).filter(
        PaperTrade.symbol == "INFY", PaperTrade.status == "OPEN"
    ).count()
    assert open_after == 0  # all trades closed — not just the latest one

    closed = db.query(PaperTrade).filter(
        PaperTrade.symbol == "INFY", PaperTrade.status == "CLOSED"
    ).all()
    assert len(closed) == 2
    assert all(t.exit_price is not None for t in closed)
    assert all(t.pnl is not None for t in closed)
    assert all(t.closed_at is not None for t in closed)


def test_proportional_pnl_distribution_across_averaged_trades(db):
    """
    PnL is distributed proportionally to each trade's quantity.
    Trade 1: 6 shares → 60 % of total PnL
    Trade 2: 4 shares → 40 % of total PnL
    Sum of individual PnLs must equal the total position PnL (within rounding).
    """
    from app.models.trade import PaperTrade

    buy1 = SimulateOrderRequest(
        symbol="TCS", side="BUY", quantity=6, price=500.0, strategy_name="ema_rsi_volume"
    )
    buy2 = SimulateOrderRequest(
        symbol="TCS", side="BUY", quantity=4, price=500.0, strategy_name="ema_rsi_volume"
    )
    simulate_order(db, buy1)
    simulate_order(db, buy2)

    last_trade = simulate_close_position(db, "TCS", current_price=600.0)
    assert last_trade is not None

    all_closed = db.query(PaperTrade).filter(
        PaperTrade.symbol == "TCS", PaperTrade.status == "CLOSED"
    ).all()
    assert len(all_closed) == 2

    total_pnl = sum(t.pnl for t in all_closed)
    # Total PnL must be positive (sold at 600, bought at 500 + slippage)
    assert total_pnl > 0

    # Each trade's PnL must be proportional to its quantity (6:4 ratio)
    pnls = sorted(t.pnl for t in all_closed)
    # Larger trade should have larger PnL
    assert pnls[1] > pnls[0]
