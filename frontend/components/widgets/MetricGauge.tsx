"use client";
import clsx from "clsx";

export function MetricGauge({ label, value, unit = "%" }: { label: string; value: number; unit?: string }) {
  const pct = Math.min(100, Math.max(0, value));
  const color = pct > 85 ? "bg-danger" : pct > 65 ? "bg-warn" : "bg-ok";
  return (
    <div className="card">
      <div className="flex justify-between items-baseline mb-2">
        <span className="text-xs text-neutral-400">{label}</span>
        <span className="text-lg font-semibold">
          {value.toFixed(1)}
          {unit}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div className={clsx("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
