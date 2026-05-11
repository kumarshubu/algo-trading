"use client";

import { useApi } from "@/hooks/useApi";
import { analyticsService, tradingService } from "@/services/api";
import StatCard from "@/components/StatCard";
import AreaChart from "@/components/AreaChart";
import TradesTable from "@/components/TradesTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";

function fmt(n: number, decimals = 2) {
  return n.toFixed(decimals);
}

function fmtInr(n: number) {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function fmtPct(n: number) {
  return `${n.toFixed(2)}%`;
}

function pnlColor(n: number) {
  return n >= 0 ? "var(--green)" : "var(--red)";
}

export default function AnalyticsPage() {
  const { data: summary, loading, error } = useApi(
    () => analyticsService.getSummary(),
    []
  );
  const { data: equityCurve } = useApi(() => analyticsService.getEquityCurve(), []);
  const { data: drawdownCurve } = useApi(() => analyticsService.getDrawdownCurve(), []);
  const { data: symbolStats } = useApi(() => analyticsService.getSymbolAnalytics(), []);
  const { data: trades } = useApi(() => tradingService.getTrades(undefined, undefined, 20), []);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} />;
  if (!summary) return null;

  const noTrades = summary.total_trades === 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Analytics
        </h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
          Paper trading performance metrics — no real money
        </p>
      </div>

      {/* ── Top metric cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <StatCard
          label="Portfolio Value"
          value={fmtInr(summary.portfolio_value)}
          subtitle={`${summary.total_return_pct >= 0 ? "+" : ""}${fmtPct(summary.total_return_pct)} return`}
          valueColor={pnlColor(summary.total_return_pct)}
        />
        <StatCard
          label="Total Realized P&L"
          value={`${summary.total_realized_pnl >= 0 ? "+" : ""}${fmtInr(summary.total_realized_pnl)}`}
          subtitle={`Unrealized: ${summary.unrealized_pnl >= 0 ? "+" : ""}₹${fmt(summary.unrealized_pnl)}`}
          valueColor={pnlColor(summary.total_realized_pnl)}
        />
        <StatCard
          label="Win Rate"
          value={noTrades ? "—" : fmtPct(summary.win_rate * 100)}
          subtitle={noTrades ? "No trades yet" : `${summary.winning_trades}W / ${summary.losing_trades}L of ${summary.total_trades}`}
          valueColor={summary.win_rate >= 0.5 ? "var(--green)" : "var(--red)"}
        />
        <StatCard
          label="Profit Factor"
          value={summary.profit_factor != null ? fmt(summary.profit_factor) : "—"}
          subtitle="Gross profit / gross loss"
          valueColor={summary.profit_factor != null && summary.profit_factor >= 1.5 ? "var(--green)" : undefined}
        />
        <StatCard
          label="Max Drawdown"
          value={fmtPct(summary.max_drawdown_pct)}
          subtitle={`Current: ${fmtPct(summary.current_drawdown_pct)}`}
          valueColor={summary.max_drawdown_pct > 10 ? "var(--red)" : undefined}
        />
        <StatCard
          label="Open Positions"
          value={summary.open_positions_count}
          subtitle={`Cash: ${fmtInr(summary.virtual_balance)}`}
        />
      </div>

      {/* ── Secondary metrics ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Expectancy / Trade"
          value={noTrades ? "—" : `₹${fmt(summary.expectancy)}`}
          subtitle="(Avg win × win%) − (Avg loss × loss%)"
          valueColor={summary.expectancy > 0 ? "var(--green)" : "var(--red)"}
        />
        <StatCard
          label="Avg Profit"
          value={noTrades ? "—" : `₹${fmt(summary.avg_profit_per_trade)}`}
          subtitle={`Avg loss: ₹${fmt(summary.avg_loss_per_trade)}`}
        />
        <StatCard
          label="Best Trade"
          value={noTrades ? "—" : `₹${fmt(summary.largest_win)}`}
          subtitle={`Worst: ₹${fmt(summary.largest_loss)}`}
          valueColor="var(--green)"
        />
        <StatCard
          label="Win Streak"
          value={noTrades ? "—" : `${summary.max_win_streak} max`}
          subtitle={`Loss streak: ${summary.max_loss_streak} max`}
        />
      </div>

      {/* ── Charts ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          className="rounded-lg p-4"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
            Equity Curve
          </h2>
          <AreaChart
            data={equityCurve || []}
            height={220}
            lineColor="#3b82f6"
            topColor="#3b82f620"
            title="Equity Curve"
            formatValue={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          />
        </div>

        <div
          className="rounded-lg p-4"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
            Drawdown %
          </h2>
          <AreaChart
            data={drawdownCurve || []}
            height={220}
            lineColor="#ef4444"
            topColor="#ef444430"
            title="Drawdown"
            formatValue={(v) => `${v.toFixed(2)}%`}
          />
        </div>
      </div>

      {/* ── Symbol performance table ── */}
      {symbolStats && symbolStats.length > 0 && (
        <div
          className="rounded-lg p-4"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
            Symbol Performance
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ color: "var(--text-secondary)", borderBottom: "1px solid var(--border)" }}>
                  <th className="text-left py-2 pr-4">Symbol</th>
                  <th className="text-right py-2 pr-4">Trades</th>
                  <th className="text-right py-2 pr-4">Win Rate</th>
                  <th className="text-right py-2 pr-4">Total P&L</th>
                  <th className="text-right py-2 pr-4">Avg P&L</th>
                  <th className="text-right py-2">Best</th>
                </tr>
              </thead>
              <tbody>
                {symbolStats.map((s) => (
                  <tr key={s.symbol} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="py-2 pr-4 font-medium" style={{ color: "var(--text-primary)" }}>
                      {s.symbol}
                    </td>
                    <td className="text-right py-2 pr-4" style={{ color: "var(--text-secondary)" }}>
                      {s.total_trades}
                    </td>
                    <td className="text-right py-2 pr-4" style={{ color: s.win_rate >= 0.5 ? "var(--green)" : "var(--red)" }}>
                      {fmtPct(s.win_rate * 100)}
                    </td>
                    <td className="text-right py-2 pr-4 font-medium" style={{ color: pnlColor(s.total_pnl) }}>
                      {s.total_pnl >= 0 ? "+" : ""}₹{fmt(s.total_pnl)}
                    </td>
                    <td className="text-right py-2 pr-4" style={{ color: pnlColor(s.avg_pnl) }}>
                      {s.avg_pnl >= 0 ? "+" : ""}₹{fmt(s.avg_pnl)}
                    </td>
                    <td className="text-right py-2" style={{ color: "var(--green)" }}>
                      ₹{fmt(s.best_trade)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Recent trades ── */}
      <div
        className="rounded-lg p-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
          Recent Trades
        </h2>
        <TradesTable trades={trades || []} />
      </div>

      {/* ── Empty state nudge ── */}
      {noTrades && (
        <div
          className="rounded-lg p-6 text-center"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            No closed trades yet. Load candle data, run the scheduler, then execute a signal to see analytics.
          </p>
          <div className="flex justify-center gap-3 mt-3">
            <a
              href="/strategies"
              className="text-xs px-3 py-1.5 rounded"
              style={{ background: "var(--accent)", color: "white" }}
            >
              Run Backtest
            </a>
            <a
              href="http://127.0.0.1:8000/api/v1/scheduler/run-once"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-3 py-1.5 rounded"
              style={{ background: "var(--surface-2)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
            >
              Trigger Scheduler
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
