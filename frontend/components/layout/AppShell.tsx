"use client";
import { AuthGuard } from "./AuthGuard";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex">
        <Sidebar />
        <div className="flex-1 min-h-screen">
          <Topbar title={title} />
          <main className="p-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
