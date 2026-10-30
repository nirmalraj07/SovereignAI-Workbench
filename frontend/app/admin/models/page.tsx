"use client";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api-client";
import clsx from "clsx";

export default function ModelsAdminPage() {
  const { data: models, isLoading } = useQuery({
    queryKey: ["admin-models"],
    queryFn: api.admin.listModels,
    refetchInterval: 10000,
  });

  return (
    <AppShell title="Model Management">
      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {models?.map((m) => (
          <div key={m.name} className="card">
            <div className="flex justify-between items-start mb-2">
              <span className="font-medium text-sm">{m.name}</span>
              <span
                className={clsx(
                  "badge",
                  m.status === "online" && "bg-ok/20 text-ok",
                  m.status === "offline" && "bg-danger/20 text-danger",
                  m.status === "unknown" && "bg-white/10 text-neutral-400"
                )}
              >
                {m.status}
              </span>
            </div>
            <div className="text-xs text-neutral-500 mb-2">
              {m.backend_type} · {m.modality}
            </div>
            <div className="flex flex-wrap gap-1">
              {m.good_for.map((tag) => (
                <span key={tag} className="text-[10px] bg-white/5 rounded-full px-2 py-0.5 text-neutral-400">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
