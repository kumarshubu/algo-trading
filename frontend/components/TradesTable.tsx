"use client";

import type { PaperTrade } from "@/types";

interface TradesTableProps {
  trades: PaperTrade[];
}

export default function TradesTable({ trades }: TradesTableProps) {
  if (trades.length === 0) {
    return (
      <div className="text-sm text-center py-6" style={{ color: "var(--text-secondary)" }}>
        No trades yet
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ color: "var(--text-secondary)", borderBottom: "1px solid var(--border)" }}>
            <th className="text-left py-2 pr-3">Symbol</th>
            <th className="text-left py-2 pr-3">Side</th>
            <th className="text-right py-2 pr-3">Entry</th>
            <th className="text-right py-2 pr-3">Exit</th>
            <th className="text-right py-2 pr-3">Qty</th>
            <th className="text-right py-2 pr-3">P&L</th>
            <th className="text-left py-2 pr-3">Status</th>
            <th className="text-left py-2">Strategy</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} style={{ borderBottom: "1px solid var(--border)" }}>
              <td className="py-2 pr-3 font-medium" style={{ color: "var(--text-primary)" }}>
                {t.symbol}
              </td>
              <td
                className="py-2 pr-3 font-medium"
                style={{ color: t.side === "BUY" ? "var(--green)" : "var(--red)" }}
              >
                {t.side}
              </td>
              <td className="text-right py-2 pr-3" style={{ color: "var(--text-secondary)" }}>
                ₹{t.entry_price.toFixed(2)}
              </td>
              <td className="text-right py-2 pr-3" style={{ color: "var(--text-secondary)" }}>
                {t.exit_price != null ? `₹${t.exit_price.toFixed(2)}` : "-"}
              </td>
              <td className="text-right py-2 pr-3" style={{ color: "var(--text-secondary)" }}>
                {t.quantity}
              </td>
              <td
                className="text-right py-2 pr-3 font-medium"
                style={{
                  color:
                    t.pnl == null
                      ? "var(--text-secondary)"
                      : t.pnl >= 0
                      ? "var(--green)"
                      : "var(--red)",
                }}
              >
                {t.pnl != null
                  ? `${t.pnl >= 0 ? "+" : ""}₹${t.pnl.toFixed(2)}`
                  : "-"}
              </td>
              <td className="py-2 pr-3">
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{
                    background: t.status === "OPEN" ? "#1e3a5f" : "#1a1a1a",
                    color: t.status === "OPEN" ? "#60a5fa" : "#9ca3af",
                  }}
                >
                  {t.status}
                </span>
              </td>
              <td className="py-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                {t.strategy_name}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
