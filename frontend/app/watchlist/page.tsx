"use client";

import { useState } from "react";
import { useApi } from "@/hooks/useApi";
import { watchlistService, signalService } from "@/services/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import type { WatchlistItem } from "@/types";

export default function WatchlistPage() {
  const [newSymbol, setNewSymbol] = useState("");
  const [addError, setAddError] = useState("");
  const [signals, setSignals] = useState<Record<string, string>>({});

  const { data: items, loading, error, refetch } = useApi<WatchlistItem[]>(
    () => watchlistService.getWatchlist(),
    []
  );

  const handleAdd = async () => {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) return;
    setAddError("");
    try {
      await watchlistService.addSymbol(sym);
      setNewSymbol("");
      refetch();
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : "Failed to add symbol");
    }
  };

  const handleRemove = async (symbol: string) => {
    await watchlistService.removeSymbol(symbol);
    refetch();
  };

  const fetchSignal = async (symbol: string) => {
    try {
      const s = await signalService.getSignal(symbol, "1h");
      setSignals((prev) => ({ ...prev, [symbol]: s.signal }));
    } catch {
      setSignals((prev) => ({ ...prev, [symbol]: "ERROR" }));
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Watchlist
        </h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
          Track symbols and check strategy signals
        </p>
      </div>

      {/* Add symbol */}
      <div
        className="rounded-lg p-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder="Symbol (e.g. RELIANCE)"
            className="flex-1 px-3 py-2 rounded text-sm"
            style={{
              background: "var(--surface-2)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
              outline: "none",
            }}
          />
          <button
            onClick={handleAdd}
            className="px-4 py-2 rounded text-sm font-medium hover:opacity-80"
            style={{ background: "var(--accent)", color: "white" }}
          >
            Add
          </button>
        </div>
        {addError && (
          <p className="text-xs mt-2" style={{ color: "var(--red)" }}>
            {addError}
          </p>
        )}
      </div>

      {/* Watchlist */}
      <div
        className="rounded-lg"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        {loading ? (
          <LoadingSpinner />
        ) : error ? (
          <div className="p-4"><ErrorMessage message={error} /></div>
        ) : !items || items.length === 0 ? (
          <div className="p-6 text-center text-sm" style={{ color: "var(--text-secondary)" }}>
            No symbols in watchlist. Add some above.
          </div>
        ) : (
          <div>
            {items.map((item, idx) => (
              <div
                key={item.id}
                className="flex items-center justify-between px-4 py-3"
                style={{
                  borderBottom: idx < items.length - 1 ? "1px solid var(--border)" : "none",
                }}
              >
                <div>
                  <span className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>
                    {item.symbol}
                  </span>
                  <span className="text-xs ml-2" style={{ color: "var(--text-secondary)" }}>
                    NSE
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {signals[item.symbol] && (
                    <span
                      className="text-xs px-2 py-0.5 rounded font-medium"
                      style={{
                        background:
                          signals[item.symbol] === "BUY"
                            ? "#14532d"
                            : signals[item.symbol] === "SELL"
                            ? "#7f1d1d"
                            : "#1c1917",
                        color:
                          signals[item.symbol] === "BUY"
                            ? "#4ade80"
                            : signals[item.symbol] === "SELL"
                            ? "#fca5a5"
                            : "#a8a29e",
                      }}
                    >
                      {signals[item.symbol]}
                    </span>
                  )}

                  <button
                    onClick={() => fetchSignal(item.symbol)}
                    className="text-xs px-2 py-1 rounded hover:opacity-80"
                    style={{
                      background: "var(--surface-2)",
                      color: "var(--text-secondary)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    Signal
                  </button>

                  <button
                    onClick={() => handleRemove(item.symbol)}
                    className="text-xs px-2 py-1 rounded hover:opacity-80"
                    style={{
                      background: "#1c1917",
                      color: "#a8a29e",
                      border: "1px solid #44403c",
                    }}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
