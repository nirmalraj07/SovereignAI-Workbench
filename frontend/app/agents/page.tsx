"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { useTaskWebSocket } from "@/hooks/useTaskWebSocket";
import { api } from "@/lib/api-client";
import clsx from "clsx";

const AGENT_NAMES = [
  "planning", "research", "knowledge_base", "coding", "ocr", "vision",
  "document", "spreadsheet", "presentation", "calculation", "validation",
  "reporting", "approval_note", "monitoring",
];

export default function AgentsPage() {
  const [watchTaskId, setWatchTaskId] = useState("");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const { status, connected } = useTaskWebSocket(activeTaskId);

  const { data: metrics } = useQuery({
    queryKey: ["system-metrics-agents"],
    queryFn: api.monitoring.system,
    refetchInterval: 5000,
  });

  return (
    <AppShell title="Agent Monitoring Dashboard">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="card lg:col-span-2">
          <h2 className="text-sm font-medium mb-3">Registered agents</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {AGENT_NAMES.map((name) => (
              <div key={name} className="flex items-center justify-between text-xs bg-surface rounded-lg px-3 py-2">
                <span className="text-neutral-300">{name}</span>
                <span className="badge bg-ok/20 text-ok">ready</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h2 className="text-sm font-medium mb-3">Host resources</h2>
          {metrics ? (
            <div className="space-y-2 text-xs text-neutral-400">
              <div>CPU: {metrics.cpu_percent.toFixed(1)}%</div>
              <div>RAM: {metrics.memory_percent.toFixed(1)}% ({metrics.memory_used_gb}/{metrics.memory_total_gb} GB)</div>
              <div>Disk: {metrics.disk_percent.toFixed(1)}%</div>
              <div>GPUs: {metrics.gpus.length}</div>
            </div>
          ) : (
            <p className="text-xs text-neutral-500">Loading…</p>
          )}
        </div>
      </div>

      <div className="card">
        <h2 className="text-sm font-medium mb-3">Watch a running task</h2>
        <div className="flex gap-2 mb-4">
          <input
            className="input-field"
            placeholder="Paste a task_id from AI Chat or OCR/Vision workspace"
            value={watchTaskId}
            onChange={(e) => setWatchTaskId(e.target.value)}
          />
          <button className="btn-primary" onClick={() => setActiveTaskId(watchTaskId)}>
            Watch
          </button>
        </div>

        {activeTaskId && (
          <>
            <p className="text-[11px] text-neutral-500 mb-2">{connected ? "Live" : "Connecting…"}</p>
            {status?.result?.plan?.map((node) => (
              <div key={node.id} className="flex items-center justify-between text-xs border-b border-white/5 py-2">
                <span>{node.id} <span className="text-neutral-600">({node.agent})</span></span>
                <span
                  className={clsx(
                    "badge",
                    node.status === "done" && "bg-ok/20 text-ok",
                    node.status === "failed" && "bg-danger/20 text-danger",
                    node.status === "running" && "bg-warn/20 text-warn",
                    node.status === "pending" && "bg-white/10 text-neutral-400"
                  )}
                >
                  {node.status}
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </AppShell>
  );
}
