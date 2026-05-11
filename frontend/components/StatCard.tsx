interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  valueColor?: string;
}

export default function StatCard({ label, value, subtitle, valueColor }: StatCardProps) {
  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <div className="text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
        {label}
      </div>
      <div
        className="text-xl font-semibold"
        style={{ color: valueColor || "var(--text-primary)" }}
      >
        {value}
      </div>
      {subtitle && (
        <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
          {subtitle}
        </div>
      )}
    </div>
  );
}
