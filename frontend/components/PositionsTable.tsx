"use client";

import type { PaperPosition } from "@/types";

interface PositionsTableProps {
  positions: PaperPosition[];
  onClose?: (symbol: string) => void;
}

export default function PositionsTable({ positions, onClose }: PositionsTableProps) {
  if (positions.length === 0) {
    return (
      <div className="text-sm text-center py-6" style={{ color: "var(--text-secondary)" }}>
        No open positions
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ color: "var(--text-secondary)", borderBottom: "1px solid var(--border)" }}>
            <th className="text-left py-2 pr-4">Symbol</th>
            <th className="text-right py-2 pr-4">Qty</th>
            <th className="text-right py-2 pr-4">Avg Price</th>
            <th className="text-right py-2 pr-4">Unrealized P&L</th>
            {onClose && <th className="text-right py-2">Action</th>}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr
              key={p.id}
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <td className="py-2 pr-4 font-medium" style={{ color: "var(--text-primary)" }}>
                {p.symbol}
              </td>
              <td className="text-right py-2 pr-4" style={{ color: "var(--text-secondary)" }}>
                {p.quantity}
              </td>
              <td className="text-right py-2 pr-4" style={{ color: "var(--text-secondary)" }}>
                ₹{p.average_price.toFixed(2)}
              </td>
              <td
                className="text-right py-2 pr-4 font-medium"
                style={{ color: p.unrealized_pnl >= 0 ? "var(--green)" : "var(--red)" }}
              >
                {p.unrealized_pnl >= 0 ? "+" : ""}₹{p.unrealized_pnl.toFixed(2)}
              </td>
              {onClose && (
                <td className="text-right py-2">
                  <button
                    onClick={() => onClose(p.symbol)}
                    className="text-xs px-2 py-1 rounded hover:opacity-80"
                    style={{ background: "#7f1d1d", color: "#fca5a5", border: "1px solid #991b1b" }}
                  >
                    Close
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
