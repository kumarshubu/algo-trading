"use client";

import { useState } from "react";
import { useApi } from "@/hooks/useApi";
import { strategyService, backtestService, candleService } from "@/services/api";
import LoadingSpinner from "@/components/LoadingSpinner";

const SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"];
const TIMEFRAMES = ["15m", "1h", "1d"];

export default function StrategiesPage() {
  const [btSymbol, setBtSymbol] = useState("RELIANCE");
  const [btTimeframe, setBtTimeframe] = useState("1h");
  const [btResult, setBtResult] = useState<Record<string, unknown> | null>(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btError, setBtError] = useState("");

  const { data: strategies, loading, refetch } = useApi(
    () => strategyService.listStrategies(),
    []
  );

  const toggle = async (name: string, currentEnabled: boolean) => {
    await strategyService.toggleStrategy(name, !currentEnabled);
    refetch();
  };

  const runBacktest = async () => {
    setBtLoading(true);
    setBtError("");
    setBtResult(null);
    try {
      // First load sample data if needed
      await candleService.fetchAndStore(btSymbol, btTimeframe, true);
      const result = await backtestService.run(btSymbol, btTimeframe);
      setBtResult(result);
    } catch (e: unknown) {
      setBtError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setBtLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Strategies
        </h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
          Manage and backtest paper trading strategies
        </p>
      </div>

      {/* Strategy list */}
      <div
        className="rounded-lg p-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
          Available Strategies
        </h2>

        {loading ? (
          <LoadingSpinner size={20} />
        ) : (
          <div className="space-y-2">
            {(strategies || []).map((s) => (
              <div
                key={s.id}
                className="rounded-lg p-4"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>
                      {s.name}
                    </div>
                    <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                      EMA20 &gt; EMA50, RSI &gt; 60, Volume &gt; 1.5x average
                    </div>
                  </div>
                  <button
                    onClick={() => toggle(s.name, s.enabled)}
                    className="text-xs px-3 py-1 rounded hover:opacity-80"
                    style={{
                      background: s.enabled ? "#14532d" : "#1c1917",
                      color: s.enabled ? "#4ade80" : "#a8a29e",
                      border: `1px solid ${s.enabled ? "#166534" : "#44403c"}`,
                    }}
                  >
                    {s.enabled ? "Kill Switch" : "Enable"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Backtesting */}
      <div
        className="rounded-lg p-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
          Run Backtest
        </h2>

        <div className="flex items-center gap-2 mb-4">
          <select
            value={btSymbol}
            onChange={(e) => setBtSymbol(e.target.value)}
            className="text-sm px-2 py-1.5 rounded"
            style={{
              background: "var(--surface-2)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
          >
            {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>

          <select
            value={btTimeframe}
            onChange={(e) => setBtTimeframe(e.target.value)}
            className="text-sm px-2 py-1.5 rounded"
            style={{
              background: "var(--surface-2)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
          >
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
          </select>

          <button
            onClick={runBacktest}
            disabled={btLoading}
            className="px-4 py-1.5 rounded text-sm font-medium hover:opacity-80 disabled:opacity-50"
            style={{ background: "var(--accent)", color: "white" }}
          >
            {btLoading ? "Running..." : "Run Backtest"}
          </button>
        </div>

        {btError && (
          <div className="text-sm mb-3" style={{ color: "var(--red)" }}>
            {btError}
          </div>
        )}

        {btLoading && <LoadingSpinner />}

        {btResult && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              { label: "Symbol", value: String(btResult.symbol) },
              { label: "Strategy", value: String(btResult.strategy) },
              { label: "Total Trades", value: String(btResult.total_trades) },
              {
                label: "Win Rate",
                value: `${btResult.win_rate_pct}%`,
                color: Number(btResult.win_rate_pct) >= 50 ? "var(--green)" : "var(--red)",
              },
              {
                label: "Total P&L",
                value: `₹${btResult.total_pnl}`,
                color: Number(btResult.total_pnl) >= 0 ? "var(--green)" : "var(--red)",
              },
              { label: "Max Drawdown", value: `${btResult.max_drawdown_pct}%`, color: "var(--red)" },
              { label: "Final Balance", value: `₹${btResult.final_balance}` },
              { label: "Start Date", value: String(btResult.start_date || "-").slice(0, 10) },
              { label: "End Date", value: String(btResult.end_date || "-").slice(0, 10) },
            ].map(({ label, value, color }) => (
              <div
                key={label}
                className="rounded-md p-3"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
              >
                <div className="text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
                  {label}
                </div>
                <div className="text-sm font-semibold" style={{ color: color || "var(--text-primary)" }}>
                  {value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
