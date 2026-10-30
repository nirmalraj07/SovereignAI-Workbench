export function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="card">
      <div className="text-xs text-neutral-400">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {hint && <div className="text-[11px] text-neutral-500 mt-1">{hint}</div>}
    </div>
  );
}
