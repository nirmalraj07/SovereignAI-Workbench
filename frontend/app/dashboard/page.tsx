"use client";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { MetricGauge } from "@/components/widgets/MetricGauge";
import { StatCard } from "@/components/widgets/StatCard";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/lib/store";

export default function DashboardPage() {
  const hasRole = useAuthStore((s) => s.hasRole);

  const { data: metrics } = useQuery({
    queryKey: ["system-metrics"],
    queryFn: api.monitoring.system,
    refetchInterval: 5000,
    enabled: hasRole("engineer"),
  });

  const { data: security } = useQuery({
    queryKey: ["security-dashboard"],
    queryFn: api.security.dashboard,
    refetchInterval: 10000,
    enabled: hasRole("auditor"),
  });

  const { data: models } = useQuery({
    queryKey: ["models"],
    queryFn: api.admin.listModels,
    refetchInterval: 15000,
    enabled: hasRole("admin"),
  });

  const onlineModels = models?.filter((m) => m.status === "online").length ?? 0;

  return (
    <AppShell title="Dashboard">
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Active Models" value={models ? `${onlineModels}/${models.length}` : "—"} hint="local runtime" />
        <StatCard
          label="External Connections"
          value={security?.external_connections ?? 0}
          hint={security?.network_egress_allowed ? "egress allowed" : "egress blocked"}
        />
        <StatCard label="Audit Events (recent)" value={security?.audit_events?.length ?? 0} />
        <StatCard label="GPUs Detected" value={metrics?.gpus?.length ?? 0} />
      </div>

      {hasRole("engineer") && metrics && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <MetricGauge label="CPU Usage" value={metrics.cpu_percent} />
          <MetricGauge label="RAM Usage" value={metrics.memory_percent} />
          <MetricGauge label="Disk Usage" value={metrics.disk_percent} />
        </div>
      )}

      {hasRole("engineer") && metrics && metrics.gpus.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {metrics.gpus.map((gpu) => (
            <MetricGauge key={gpu.index} label={`GPU ${gpu.index}: ${gpu.name}`} value={gpu.utilization_pct} />
          ))}
        </div>
      )}

      {hasRole("auditor") && security && (
        <div className="card">
          <h2 className="text-sm font-medium mb-3">Recent Audit Events</h2>
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {security.audit_events.length === 0 && (
              <p className="text-xs text-neutral-500">No audit events yet.</p>
            )}
            {security.audit_events.map((event, i) => (
              <div key={i} className="flex justify-between text-xs border-b border-white/5 pb-2">
                <span className="text-neutral-300">{event.action}</span>
                <span className="text-neutral-500">{event.resource}</span>
                <span className="text-neutral-600">{new Date(event.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </AppShell>
  );
}
