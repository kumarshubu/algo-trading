"use client";

import { useApi } from "@/hooks/useApi";
import { strategyService } from "@/services/api";
import LoadingSpinner from "./LoadingSpinner";

export default function StrategyStatusWidget() {
  const { data: strategies, loading, error, refetch } = useApi(
    () => strategyService.listStrategies(),
    []
  );

  const toggle = async (name: string, currentEnabled: boolean) => {
    await strategyService.toggleStrategy(name, !currentEnabled);
    refetch();
  };

  if (loading) return <LoadingSpinner size={20} />;
  if (error) return <div className="text-xs" style={{ color: "var(--red)" }}>Failed to load strategies</div>;

  return (
    <div className="space-y-2">
      {(strategies || []).map((s) => (
        <div
          key={s.id}
          className="flex items-center justify-between rounded-md px-3 py-2"
          style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
        >
          <div>
            <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
              {s.name}
            </div>
            <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {s.enabled ? "Running" : "Stopped"}
            </div>
          </div>
          <button
            onClick={() => toggle(s.name, s.enabled)}
            className="text-xs px-2 py-1 rounded transition-opacity hover:opacity-80"
            style={{
              background: s.enabled ? "#14532d" : "#1c1917",
              color: s.enabled ? "#4ade80" : "#a8a29e",
              border: `1px solid ${s.enabled ? "#166534" : "#44403c"}`,
            }}
          >
            {s.enabled ? "Enabled" : "Disabled"}
          </button>
        </div>
      ))}
    </div>
  );
}
