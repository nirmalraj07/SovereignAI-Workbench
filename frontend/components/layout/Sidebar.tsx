"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare, ScanText, Eye, Database, Code2, FileOutput, Bot,
  ShieldAlert, Users, Cpu, ScrollText, Settings, LayoutDashboard,
} from "lucide-react";
import { useAuthStore, useUIStore } from "@/lib/store";
import type { Role } from "@/types";
import clsx from "clsx";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  minRole: Role;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, minRole: "viewer" },
  { href: "/chat", label: "AI Chat", icon: MessageSquare, minRole: "viewer" },
  { href: "/ocr", label: "OCR Workspace", icon: ScanText, minRole: "engineer" },
  { href: "/vision", label: "Vision Workspace", icon: Eye, minRole: "engineer" },
  { href: "/knowledge", label: "Knowledge Search", icon: Database, minRole: "viewer" },
  { href: "/coding", label: "Coding Workspace", icon: Code2, minRole: "engineer" },
  { href: "/files", label: "Generated Files", icon: FileOutput, minRole: "viewer" },
  { href: "/agents", label: "Agent Monitor", icon: Bot, minRole: "engineer" },
  { href: "/security", label: "Security Monitor", icon: ShieldAlert, minRole: "auditor" },
  { href: "/admin/users", label: "User Management", icon: Users, minRole: "admin" },
  { href: "/admin/models", label: "Model Management", icon: Cpu, minRole: "admin" },
  { href: "/audit", label: "Audit Logs", icon: ScrollText, minRole: "auditor" },
  { href: "/settings", label: "Settings", icon: Settings, minRole: "viewer" },
];

export function Sidebar() {
  const pathname = usePathname();
  const hasRole = useAuthStore((s) => s.hasRole);
  const user = useAuthStore((s) => s.user);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggle = useUIStore((s) => s.toggleSidebar);

  return (
    <aside
      className={clsx(
        "h-screen sticky top-0 border-r border-white/5 bg-surface flex flex-col transition-all",
        collapsed ? "w-16" : "w-64"
      )}
    >
      <div className="flex items-center justify-between px-4 py-4 border-b border-white/5">
        {!collapsed && <span className="font-semibold text-sm tracking-wide">SovereignAI</span>}
        <button onClick={toggle} className="text-neutral-400 hover:text-white text-xs">
          {collapsed ? "»" : "«"}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_ITEMS.filter((item) => hasRole(item.minRole)).map((item) => {
          const Icon = item.icon;
          const active = pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 px-4 py-2.5 text-sm mx-2 rounded-lg mb-0.5 transition-colors",
                active ? "bg-accent/15 text-accent" : "text-neutral-300 hover:bg-white/5"
              )}
            >
              <Icon size={18} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {!collapsed && user && (
        <div className="px-4 py-3 border-t border-white/5 text-xs text-neutral-400">
          <div className="font-medium text-neutral-200">{user.username}</div>
          <div className="uppercase tracking-wide">{user.role}</div>
        </div>
      )}
    </aside>
  );
}
