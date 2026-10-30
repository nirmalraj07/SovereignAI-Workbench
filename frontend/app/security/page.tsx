"use client";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { StatCard } from "@/components/widgets/StatCard";
import { api } from "@/lib/api-client";
import { ShieldCheck, ShieldAlert } from "lucide-react";

export default function SecurityPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["security-dashboard-full"],
    queryFn: api.security.dashboard,
    refetchInterval: 5000,
  });

  return (
    <AppShell title="Security Dashboard">
      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <StatCard label="External Connections" value={data.external_connections} />
            <StatCard label="External API Calls" value={data.external_api_calls} />
            <StatCard label="Audit Events (recent)" value={data.audit_events.length} />
          </div>

          <div className={`card mb-6 flex items-center gap-3 ${data.network_egress_allowed ? "border-danger/40" : "border-ok/40"}`}>
            {data.network_egress_allowed ? (
              <ShieldAlert className="text-danger" size={20} />
            ) : (
              <ShieldCheck className="text-ok" size={20} />
            )}
            <div>
              <div className="text-sm font-medium">
                {data.network_egress_allowed ? "Network egress is currently ALLOWED" : "Network egress is blocked"}
              </div>
              <div className="text-xs text-neutral-500">
                The platform network is configured as internal-only; this reflects the live policy state.
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-sm font-medium mb-3">Audit event stream</h2>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-neutral-500 text-left border-b border-white/5">
                  <th className="py-2">Action</th>
                  <th className="py-2">Resource</th>
                  <th className="py-2">IP</th>
                  <th className="py-2">Time</th>
                </tr>
              </thead>
              <tbody>
                {data.audit_events.map((e, i) => (
                  <tr key={i} className="border-b border-white/5">
                    <td className="py-2 text-neutral-300">{e.action}</td>
                    <td className="py-2 text-neutral-400">{e.resource}</td>
                    <td className="py-2 text-neutral-500">{e.ip}</td>
                    <td className="py-2 text-neutral-600">{new Date(e.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AppShell>
  );
}
