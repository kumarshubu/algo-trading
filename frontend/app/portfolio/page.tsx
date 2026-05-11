"use client";

import { useState } from "react";
import { useApi, usePolling } from "@/hooks/useApi";
import { tradingService } from "@/services/api";
import StatCard from "@/components/StatCard";
import PositionsTable from "@/components/PositionsTable";
import TradesTable from "@/components/TradesTable";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function PortfolioPage() {
  const [activeTab, setActiveTab] = useState<"positions" | "trades">("positions");
  const [resetStatus, setResetStatus] = useState("");

  const {
    data: portfolio,
    loading: portfolioLoading,
    refetch: refetchPortfolio,
  } = usePolling(() => tradingService.getPortfolio(), 10000, []);

  const { data: positions, refetch: refetchPositions } = useApi(
    () => tradingService.getPositions(),
    []
  );

  const { data: trades } = useApi(
    () => tradingService.getTrades(undefined, undefined, 100),
    []
  );

  const handleClose = async (symbol: string) => {
    const price = prompt(`Enter current price for ${symbol}:`);
    if (!price) return;
    const numPrice = parseFloat(price);
    if (isNaN(numPrice) || numPrice <= 0) return alert("Invalid price");
    await tradingService.closePosition(symbol, numPrice);
    refetchPositions();
    refetchPortfolio();
  };

  const handleReset = async () => {
    if (!confirm("Reset portfolio? This clears all trades and positions.")) return;
    await tradingService.resetPortfolio();
    setResetStatus("Portfolio reset");
    refetchPortfolio();
    refetchPositions();
    setTimeout(() => setResetStatus(""), 3000);
  };

  const returnPct = portfolio
    ? ((portfolio.portfolio_value - portfolio.initial_balance) / portfolio.initial_balance) * 100
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Paper Portfolio
          </h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
            Simulated portfolio — PAPER TRADING ONLY
          </p>
        </div>
        <div className="flex items-center gap-2">
          {resetStatus && (
            <span className="text-xs" style={{ color: "var(--green)" }}>
              {resetStatus}
            </span>
          )}
          <button
            onClick={handleReset}
            className="text-xs px-3 py-1.5 rounded hover:opacity-80"
            style={{
              background: "#1c1917",
              color: "#a8a29e",
              border: "1px solid #44403c",
            }}
          >
            Reset Portfolio
          </button>
        </div>
      </div>

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
            subtitle={`${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}% return`}
            valueColor={returnPct >= 0 ? "var(--green)" : "var(--red)"}
          />
          <StatCard
            label="Realized P&L"
            value={`${portfolio.total_realized_pnl >= 0 ? "+" : ""}₹${portfolio.total_realized_pnl.toFixed(2)}`}
            valueColor={portfolio.total_realized_pnl >= 0 ? "var(--green)" : "var(--red)"}
          />
          <StatCard
            label="Unrealized P&L"
            value={`${portfolio.total_unrealized_pnl >= 0 ? "+" : ""}₹${portfolio.total_unrealized_pnl.toFixed(2)}`}
            valueColor={portfolio.total_unrealized_pnl >= 0 ? "var(--green)" : "var(--red)"}
            subtitle={`Daily loss: ₹${portfolio.daily_loss.toFixed(2)}`}
          />
        </div>
      ) : null}

      {/* Tabs */}
      <div
        className="rounded-lg"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div
          className="flex"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          {(["positions", "trades"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="px-4 py-3 text-sm font-medium capitalize"
              style={{
                color: activeTab === tab ? "var(--text-primary)" : "var(--text-secondary)",
                borderBottom: activeTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
              }}
            >
              {tab}
              {tab === "positions" && positions ? ` (${positions.length})` : ""}
              {tab === "trades" && trades ? ` (${trades.length})` : ""}
            </button>
          ))}
        </div>

        <div className="p-4">
          {activeTab === "positions" ? (
            <PositionsTable positions={positions || []} onClose={handleClose} />
          ) : (
            <TradesTable trades={trades || []} />
          )}
        </div>
      </div>
    </div>
  );
}
