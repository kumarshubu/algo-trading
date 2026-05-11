"""
Analytics service — calculates portfolio and trade performance metrics.
All calculations are safe for empty datasets (zero trades, no snapshots, etc.).
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.trade import PaperTrade
from app.models.position import PaperPosition
from app.models.equity_snapshot import EquitySnapshot
from app.services.paper_trading import get_or_create_portfolio
from app.core.logging import get_logger

logger = get_logger(__name__)


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def get_closed_trades(db: Session) -> list[PaperTrade]:
    return (
        db.query(PaperTrade)
        .filter(PaperTrade.status.in_(["CLOSED", "STOPPED", "TARGET_HIT"]))
        .filter(PaperTrade.pnl.isnot(None))
        .order_by(PaperTrade.created_at.asc())
        .all()
    )


def calculate_streaks(trades: list[PaperTrade]) -> dict:
    """Calculate win/loss streak metrics from an ordered list of closed trades."""
    if not trades:
        return {
            "max_win_streak": 0,
            "max_loss_streak": 0,
            "current_streak": 0,
            "current_streak_type": "NONE",
        }

    max_win = 0
    max_loss = 0
    cur = 0
    cur_type = "NONE"

    for trade in trades:
        is_win = (trade.pnl or 0) > 0
        if is_win:
            if cur_type == "WIN":
                cur += 1
            else:
                cur = 1
                cur_type = "WIN"
            max_win = max(max_win, cur)
        else:
            if cur_type == "LOSS":
                cur += 1
            else:
                cur = 1
                cur_type = "LOSS"
            max_loss = max(max_loss, cur)

    return {
        "max_win_streak": max_win,
        "max_loss_streak": max_loss,
        "current_streak": cur,
        "current_streak_type": cur_type,
    }


def calculate_drawdown_series(snapshots: list[EquitySnapshot]) -> list[dict]:
    """
    Calculate drawdown percentage at each equity snapshot point.
    Drawdown = (peak_so_far - current_value) / peak_so_far * 100
    """
    if not snapshots:
        return []

    peak = snapshots[0].balance
    result = []

    for s in snapshots:
        portfolio_value = s.balance + s.unrealized_pnl
        if portfolio_value > peak:
            peak = portfolio_value
        dd = _safe_div(peak - portfolio_value, peak, 0.0) * 100
        result.append({
            "time": int(s.timestamp.replace(tzinfo=timezone.utc).timestamp()),
            "value": round(dd, 4),
        })

    return result


def get_summary(db: Session) -> dict:
    """
    Compute all major metrics. Returns safe defaults when no data is available.
    Never raises.
    """
    try:
        return _compute_summary(db)
    except Exception as e:
        logger.error("analytics_summary_error", error_type=type(e).__name__)
        return _empty_summary()


def _compute_summary(db: Session) -> dict:
    portfolio = get_or_create_portfolio(db)
    positions = db.query(PaperPosition).all()
    closed = get_closed_trades(db)

    winners = [t for t in closed if (t.pnl or 0) > 0]
    losers  = [t for t in closed if (t.pnl or 0) <= 0]

    total      = len(closed)
    n_wins     = len(winners)
    n_losses   = len(losers)
    win_rate   = _safe_div(n_wins, total)
    loss_rate  = _safe_div(n_losses, total)

    gross_profit = sum(t.pnl for t in winners)
    gross_loss   = abs(sum(t.pnl for t in losers))
    total_pnl    = gross_profit - gross_loss

    avg_win  = _safe_div(gross_profit, n_wins)
    avg_loss = _safe_div(gross_loss, n_losses)

    profit_factor = _safe_div(gross_profit, gross_loss, default=None)  # None = no losing trades
    expectancy    = (avg_win * win_rate) - (avg_loss * loss_rate)

    # Holding duration
    durations = []
    for t in closed:
        if t.closed_at and t.created_at:
            durations.append((t.closed_at - t.created_at).total_seconds() / 3600)
    avg_holding_hours = _safe_div(sum(durations), len(durations)) if durations else 0

    # Risk metrics from equity snapshots
    snapshots = (
        db.query(EquitySnapshot)
        .order_by(EquitySnapshot.timestamp.asc())
        .all()
    )
    dd_series    = calculate_drawdown_series(snapshots)
    max_drawdown = max((d["value"] for d in dd_series), default=0.0)
    cur_drawdown = dd_series[-1]["value"] if dd_series else 0.0

    # Streaks
    streaks = calculate_streaks(closed)

    # Portfolio totals
    unrealized_pnl = sum(p.unrealized_pnl for p in positions)
    portfolio_value = portfolio.virtual_balance + unrealized_pnl

    return {
        # Core trade metrics
        "total_trades": total,
        "winning_trades": n_wins,
        "losing_trades": n_losses,
        "win_rate": round(win_rate, 4),
        "loss_rate": round(loss_rate, 4),
        # PnL
        "total_realized_pnl": round(total_pnl, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "avg_profit_per_trade": round(avg_win, 2),
        "avg_loss_per_trade": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
        "expectancy": round(expectancy, 2),
        "avg_holding_hours": round(avg_holding_hours, 2),
        # Risk
        "max_drawdown_pct": round(max_drawdown, 4),
        "current_drawdown_pct": round(cur_drawdown, 4),
        "largest_win": round(max((t.pnl for t in winners), default=0.0), 2),
        "largest_loss": round(min((t.pnl for t in losers), default=0.0), 2),
        # Streaks
        **streaks,
        # Portfolio
        "portfolio_value": round(portfolio_value, 2),
        "virtual_balance": round(portfolio.virtual_balance, 2),
        "initial_balance": round(portfolio.initial_balance, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "open_positions_count": len(positions),
        "total_return_pct": round(
            _safe_div(portfolio_value - portfolio.initial_balance, portfolio.initial_balance) * 100, 4
        ),
    }


def _empty_summary() -> dict:
    return {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "win_rate": 0.0, "loss_rate": 0.0,
        "total_realized_pnl": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
        "avg_profit_per_trade": 0.0, "avg_loss_per_trade": 0.0,
        "profit_factor": None, "expectancy": 0.0, "avg_holding_hours": 0.0,
        "max_drawdown_pct": 0.0, "current_drawdown_pct": 0.0,
        "largest_win": 0.0, "largest_loss": 0.0,
        "max_win_streak": 0, "max_loss_streak": 0,
        "current_streak": 0, "current_streak_type": "NONE",
        "portfolio_value": 0.0, "virtual_balance": 0.0, "initial_balance": 0.0,
        "unrealized_pnl": 0.0, "open_positions_count": 0, "total_return_pct": 0.0,
    }


def get_equity_curve(db: Session, limit: int = 500) -> list[dict]:
    snapshots = (
        db.query(EquitySnapshot)
        .order_by(EquitySnapshot.timestamp.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "time": int(s.timestamp.replace(tzinfo=timezone.utc).timestamp()),
            "value": round(s.balance + s.unrealized_pnl, 2),
        }
        for s in snapshots
    ]


def get_drawdown_curve(db: Session, limit: int = 500) -> list[dict]:
    snapshots = (
        db.query(EquitySnapshot)
        .order_by(EquitySnapshot.timestamp.asc())
        .limit(limit)
        .all()
    )
    return calculate_drawdown_series(snapshots)


def get_symbol_analytics(db: Session) -> list[dict]:
    closed = get_closed_trades(db)
    buckets: dict[str, list[float]] = {}
    for t in closed:
        buckets.setdefault(t.symbol, []).append(t.pnl or 0.0)

    rows = []
    for symbol, pnls in sorted(buckets.items()):
        wins = [p for p in pnls if p > 0]
        rows.append({
            "symbol": symbol,
            "total_trades": len(pnls),
            "winning_trades": len(wins),
            "win_rate": round(_safe_div(len(wins), len(pnls)), 4),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(_safe_div(sum(pnls), len(pnls)), 2),
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
        })
    return sorted(rows, key=lambda r: r["total_pnl"], reverse=True)


def get_timeframe_analytics(db: Session) -> list[dict]:
    closed = get_closed_trades(db)
    buckets: dict[str, list] = {}
    for t in closed:
        # strategy_name encodes timeframe context; use signal_id lookup if needed.
        # For simplicity, group by the strategy (which includes timeframe in signals).
        # We can't easily get timeframe from PaperTrade directly unless via signal.
        # Use a fallback grouping by strategy_name.
        key = t.strategy_name
        buckets.setdefault(key, []).append(t.pnl or 0.0)

    rows = []
    for strat, pnls in sorted(buckets.items()):
        wins = [p for p in pnls if p > 0]
        rows.append({
            "strategy_name": strat,
            "total_trades": len(pnls),
            "winning_trades": len(wins),
            "win_rate": round(_safe_div(len(wins), len(pnls)), 4),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(_safe_div(sum(pnls), len(pnls)), 2),
        })
    return rows


def get_trade_streaks(db: Session) -> dict:
    closed = get_closed_trades(db)
    streaks = calculate_streaks(closed)

    # Build streak history for charting
    history = []
    cur = 0
    cur_type = "NONE"
    for t in closed:
        is_win = (t.pnl or 0) > 0
        if is_win:
            cur = cur + 1 if cur_type == "WIN" else 1
            cur_type = "WIN"
        else:
            cur = cur + 1 if cur_type == "LOSS" else 1
            cur_type = "LOSS"
        history.append({
            "trade_id": t.id,
            "symbol": t.symbol,
            "pnl": round(t.pnl or 0.0, 2),
            "result": "WIN" if is_win else "LOSS",
            "streak": cur,
        })

    return {**streaks, "history": history[-20:]}  # last 20 for the table
