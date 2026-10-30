"use client";
import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api-client";
import { useTaskWebSocket } from "@/hooks/useTaskWebSocket";
import clsx from "clsx";

export default function ChatPage() {
  const [message, setMessage] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { status, connected } = useTaskWebSocket(taskId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim()) return;
    setSubmitting(true);
    try {
      const res = await api.tasks.submit(message);
      setTaskId(res.task_id);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell title="AI Chat Workspace">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <form onSubmit={handleSubmit} className="card lg:col-span-1 h-fit space-y-3">
          <label htmlFor="chat-request" className="text-xs text-neutral-400">Request</label>
          <textarea
            id="chat-request"
            className="input-field h-40 resize-none"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="e.g. Process this scanned inspection report, or: build me an inventory management app"
          />
          <button type="submit" className="btn-primary w-full" disabled={submitting}>
            {submitting ? "Submitting…" : "Run agentic task"}
          </button>
          {taskId && (
            <p className="text-[11px] text-neutral-500">
              Task <code>{taskId.slice(0, 8)}</code> — {connected ? "live" : "connecting…"}
            </p>
          )}
        </form>

        <div className="lg:col-span-2 space-y-4">
          {!status && <p className="text-sm text-neutral-500">Submit a request to see the Planning Agent's task graph run live.</p>}

          {status && (
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium">Task state</h2>
                <span
                  className={clsx(
                    "badge",
                    status.state === "SUCCESS" && "bg-ok/20 text-ok",
                    status.state === "FAILURE" && "bg-danger/20 text-danger",
                    (status.state === "PENDING" || status.state === "STARTED") && "bg-warn/20 text-warn"
                  )}
                >
                  {status.state}
                </span>
              </div>

              {status.result?.plan && (
                <div className="space-y-2 mb-4">
                  {status.result.plan.map((node) => (
                    <div key={node.id} className="flex items-center justify-between text-xs border-b border-white/5 pb-2">
                      <span className="text-neutral-300">
                        {node.id} <span className="text-neutral-600">({node.agent})</span>
                      </span>
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
                </div>
              )}

              {status.result?.results && (
                <pre className="text-xs bg-surface rounded-lg p-3 overflow-x-auto max-h-96 overflow-y-auto">
                  {JSON.stringify(status.result.results, null, 2)}
                </pre>
              )}

              {status.error && <p className="text-danger text-xs">{status.error}</p>}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
