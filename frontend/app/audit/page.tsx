"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api-client";
import type { AuditEvent } from "@/types";

export default function AuditPage() {
  const [filter, setFilter] = useState("");
  const { data } = useQuery({
    queryKey: ["audit-log"],
    queryFn: () => api.audit.list(200) as unknown as Promise<AuditEvent[]>,
    refetchInterval: 10000,
  });

  const filtered = (data ?? []).filter(
    (e) => !filter || e.action.includes(filter) || e.resource.includes(filter)
  );

  return (
    <AppShell title="Audit Log Viewer">
      <div className="card mb-6">
        <input
          className="input-field"
          placeholder="Filter by action or resource…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className="card">
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
            {filtered.map((e, i) => (
              <tr key={i} className="border-b border-white/5">
                <td className="py-2 text-neutral-300">{e.action}</td>
                <td className="py-2 text-neutral-400">{e.resource}</td>
                <td className="py-2 text-neutral-500">{e.ip}</td>
                <td className="py-2 text-neutral-600">{new Date(e.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={4} className="py-4 text-center text-neutral-500">No matching events.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
