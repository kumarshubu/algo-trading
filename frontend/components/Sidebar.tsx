"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/strategies", label: "Strategies" },
  { href: "/analytics", label: "Analytics" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="fixed top-0 left-0 h-screen w-56 flex flex-col"
      style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}
    >
      <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
        <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          Algo Trading
        </div>
        <div
          className="text-xs mt-0.5 px-1.5 py-0.5 rounded inline-block"
          style={{ background: "#1e3a5f", color: "#60a5fa", fontSize: "10px" }}
        >
          PAPER ONLY
        </div>
      </div>

      <nav className="flex-1 p-3">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "block px-3 py-2 rounded-md text-sm mb-1 transition-colors",
                active
                  ? "font-medium"
                  : "hover:opacity-80"
              )}
              style={{
                background: active ? "var(--surface-2)" : "transparent",
                color: active ? "var(--text-primary)" : "var(--text-secondary)",
              }}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-3 text-xs" style={{ color: "var(--text-secondary)" }}>
        All trades are simulated.
        <br />
        No real money involved.
      </div>
    </aside>
  );
}
