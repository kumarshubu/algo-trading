"use client";

import { useState } from "react";
import { useApi, usePolling } from "@/hooks/useApi";
import { tradingService, candleService, signalService } from "@/services/api";
import StatCard from "@/components/StatCard";
import CandleChart from "@/components/CandleChart";
import StrategyStatusWidget from "@/components/StrategyStatusWidget";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";

const SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"];
const TIMEFRAMES = ["15m", "1h", "1d"] as const;

export default function DashboardPage() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [timeframe, setTimeframe] = useState<"15m" | "1h" | "1d">("1h");
  const [fetchStatus, setFetchStatus] = useState("");

  const { data: portfolio, loading: portfolioLoading } = usePolling(
    () => tradingService.getPortfolio(),
    30000,
    []
  );

  const { data: candles, loading: candlesLoading, error: candlesError, refetch: refetchCandles } = useApi(
    () => candleService.getCandles(symbol, timeframe),
    [symbol, timeframe]
  );

  const { data: signal } = useApi(
    () => signalService.getSignal(symbol, timeframe).catch(() => null),
    [symbol, timeframe]
  );

  const handleFetch = async () => {
    setFetchStatus("Fetching...");
    try {
      const result = await candleService.fetchAndStore(symbol, timeframe, true);
      setFetchStatus(`Loaded ${result.total_in_db} candles`);
      refetchCandles();
    } catch {
      setFetchStatus("Fetch failed");
    }
  };

  const pnlColor =
    !portfolio
      ? undefined
      : portfolio.total_realized_pnl + portfolio.total_unrealized_pnl >= 0
      ? "var(--green)"
      : "var(--red)";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Dashboard
          </h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
            Paper trading only — no real money involved
          </p>
        </div>
        {signal && (
          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
            style={{
              background: signal.signal === "BUY" ? "#14532d" : signal.signal === "SELL" ? "#7f1d1d" : "#1c1917",
              color: signal.signal === "BUY" ? "#4ade80" : signal.signal === "SELL" ? "#fca5a5" : "#a8a29e",
              border: `1px solid ${signal.signal === "BUY" ? "#166534" : signal.signal === "SELL" ? "#991b1b" : "#44403c"}`,
            }}
          >
            <span className="font-semibold">{signal.signal}</span>
            <span style={{ opacity: 0.7 }}>{symbol} • {signal.reason?.slice(0, 40)}</span>
          </div>
        )}
      </div>

      {/* Portfolio stats */}
      {portfolioLoading ? (
        <LoadingSpinner />
      ) : portfolio ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            label="Virtual Balance"
            value={`₹${portfolio.virtual_balance.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          />
          <StatCard
            label="Portfolio Value"
            value={`₹${portfolio.portfolio_value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          />
          <StatCard
            label="Total P&L"
            value={`${portfolio.total_realized_pnl >= 0 ? "+" : ""}₹${(portfolio.total_realized_pnl + portfolio.total_unrealized_pnl).toFixed(2)}`}
            valueColor={pnlColor}
          />
          <StatCard
            label="Open Positions"
            value={portfolio.open_positions_count}
            subtitle={`Daily loss: ₹${portfolio.daily_loss.toFixed(2)}`}
          />
        </div>
      ) : null}

      {/* Chart section */}
      <div
        className="rounded-lg p-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="text-sm px-2 py-1 rounded"
              style={{
                background: "var(--surface-2)",
                color: "var(--text-primary)",
                border: "1px solid var(--border)",
              }}
            >
              {SYMBOLS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>

            <div className="flex rounded overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className="text-xs px-3 py-1.5 transition-colors"
                  style={{
                    background: timeframe === tf ? "var(--accent)" : "var(--surface-2)",
                    color: timeframe === tf ? "white" : "var(--text-secondary)",
                  }}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {fetchStatus && (
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                {fetchStatus}
              </span>
            )}
            <button
              onClick={handleFetch}
              className="text-xs px-3 py-1.5 rounded hover:opacity-80"
              style={{
                background: "var(--surface-2)",
                color: "var(--text-secondary)",
                border: "1px solid var(--border)",
              }}
            >
              Load Data
            </button>
          </div>
        </div>

        {candlesLoading ? (
          <LoadingSpinner />
        ) : candlesError ? (
          <ErrorMessage message={candlesError} />
        ) : (
          <CandleChart candles={candles || []} height={400} />
        )}
      </div>

      {/* Strategy status */}
      <div
        className="rounded-lg p-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
          Strategy Status
        </h2>
        <StrategyStatusWidget />
      </div>
    </div>
  );
}
