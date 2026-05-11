"""
Simple backtesting engine.
Separated from paper trading runtime to avoid lookahead bias.

Rules:
- Strategy only sees candles UP TO the current bar (no future data)
- Each bar, the strategy gets all candles up to and including that bar
- Execution happens at the NEXT bar's open (more realistic)
- No lookahead bias by design
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd

from app.strategies.base import BaseStrategy, Signal
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestTrade:
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 0.0
    pnl: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    exit_reason: str = ""


@dataclass
class BacktestResult:
    symbol: str
    strategy_name: str
    trades: list[BacktestTrade] = field(default_factory=list)
    initial_balance: float = 100000.0
    final_balance: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self.win_rate * 100, 2),
            "total_pnl": round(self.total_pnl, 2),
            "final_balance": round(self.final_balance, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "start_date": str(self.start_date) if self.start_date else None,
            "end_date": str(self.end_date) if self.end_date else None,
        }


class BacktestEngine:
    """
    Walk-forward backtesting engine.
    At each bar, only data up to that bar is passed to the strategy.
    This prevents lookahead bias.
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_balance: float = 100000.0,
        position_size_pct: float = 0.10,  # 10% of balance per trade
        slippage_pct: float = 0.001,
        brokerage_pct: float = 0.0003,
    ):
        self.strategy = strategy
        self.initial_balance = initial_balance
        self.position_size_pct = position_size_pct
        self.slippage_pct = slippage_pct
        self.brokerage_pct = brokerage_pct

    def run(self, symbol: str, candles: pd.DataFrame) -> BacktestResult:
        """
        Run backtest on historical candle data.
        candles: DataFrame with columns [open, high, low, close, volume], index=timestamp_utc
        """
        result = BacktestResult(
            symbol=symbol,
            strategy_name=self.strategy.name,
            initial_balance=self.initial_balance,
            final_balance=self.initial_balance,
        )

        if len(candles) < 60:
            logger.warning("backtest_insufficient_data", symbol=symbol, rows=len(candles))
            return result

        result.start_date = candles.index[0].to_pydatetime() if hasattr(candles.index[0], 'to_pydatetime') else candles.index[0]
        result.end_date = candles.index[-1].to_pydatetime() if hasattr(candles.index[-1], 'to_pydatetime') else candles.index[-1]

        balance = self.initial_balance
        open_trade: Optional[BacktestTrade] = None
        peak_balance = balance
        max_drawdown = 0.0
        balance_history = [balance]

        # Walk forward - strategy only sees data up to bar i (no lookahead)
        for i in range(60, len(candles)):
            historical = candles.iloc[:i]   # ONLY past data
            current_bar = candles.iloc[i]
            current_price = float(current_bar["open"])  # execute at next bar's open

            # Check stop loss / target on open trade
            if open_trade:
                exit_reason = self._check_exits(open_trade, current_bar)
                if exit_reason:
                    trade_result = self._close_trade(open_trade, current_price, exit_reason, candles.index[i])
                    balance += trade_result.pnl or 0.0
                    result.trades.append(trade_result)
                    open_trade = None
                    balance_history.append(balance)

                    # Track drawdown
                    if balance > peak_balance:
                        peak_balance = balance
                    dd = (peak_balance - balance) / peak_balance
                    max_drawdown = max(max_drawdown, dd)
                    continue

            # Generate signal from historical data (no current bar)
            signal = self.strategy.generate_signal(symbol, historical)

            if signal.signal == Signal.BUY and open_trade is None:
                exec_price = current_price * (1 + self.slippage_pct)
                trade_value = balance * self.position_size_pct
                quantity = trade_value / exec_price
                brokerage = trade_value * self.brokerage_pct
                total_cost = trade_value + brokerage

                if balance >= total_cost:
                    balance -= total_cost
                    open_trade = BacktestTrade(
                        symbol=symbol,
                        side="BUY",
                        entry_price=exec_price,
                        quantity=quantity,
                        stop_loss=signal.stop_loss,
                        target_price=signal.target_price,
                        entry_time=candles.index[i].to_pydatetime() if hasattr(candles.index[i], 'to_pydatetime') else candles.index[i],
                    )

        # Close any open position at end of data
        if open_trade:
            last_price = float(candles.iloc[-1]["close"])
            trade_result = self._close_trade(open_trade, last_price, "END_OF_DATA", candles.index[-1])
            balance += trade_result.pnl or 0.0
            result.trades.append(trade_result)

        result.final_balance = round(balance, 2)
        result.total_pnl = round(balance - self.initial_balance, 2)
        result.total_trades = len(result.trades)
        result.winning_trades = sum(1 for t in result.trades if (t.pnl or 0) > 0)
        result.losing_trades = sum(1 for t in result.trades if (t.pnl or 0) < 0)
        result.max_drawdown = round(max_drawdown, 4)
        result.win_rate = result.winning_trades / result.total_trades if result.total_trades > 0 else 0.0

        logger.info(
            "backtest_complete",
            symbol=symbol,
            strategy=self.strategy.name,
            trades=result.total_trades,
            pnl=result.total_pnl,
            win_rate=f"{result.win_rate:.1%}",
        )
        return result

    def _check_exits(self, trade: BacktestTrade, bar: pd.Series) -> Optional[str]:
        """Check if stop loss or target is hit on this bar."""
        low = float(bar["low"])
        high = float(bar["high"])

        if trade.stop_loss and low <= trade.stop_loss:
            return "STOP_LOSS"
        if trade.target_price and high >= trade.target_price:
            return "TARGET"
        return None

    def _close_trade(
        self,
        trade: BacktestTrade,
        exit_price: float,
        reason: str,
        exit_time,
    ) -> BacktestTrade:
        exec_exit = exit_price * (1 - self.slippage_pct)
        proceeds = exec_exit * trade.quantity
        cost_basis = trade.entry_price * trade.quantity
        brokerage = proceeds * self.brokerage_pct
        pnl = proceeds - brokerage - cost_basis

        trade.exit_price = round(exec_exit, 2)
        trade.pnl = round(pnl, 2)
        trade.exit_reason = reason
        trade.exit_time = exit_time.to_pydatetime() if hasattr(exit_time, 'to_pydatetime') else exit_time
        return trade
