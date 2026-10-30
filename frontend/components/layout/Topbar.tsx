"use client";
import { Bell, LogOut, Moon, Sun } from "lucide-react";
import { useAuthStore, useUIStore } from "@/lib/store";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function Topbar({ title }: { title: string }) {
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);
  const darkMode = useUIStore((s) => s.darkMode);
  const toggleDark = useUIStore((s) => s.toggleDarkMode);

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: api.notifications.list,
    refetchInterval: 15_000,
  });
  const unread = notifications?.filter((n) => !n.read).length ?? 0;

  return (
    <header className="h-14 border-b border-white/5 flex items-center justify-between px-6 sticky top-0 bg-surface/90 backdrop-blur z-10">
      <h1 className="text-sm font-medium text-neutral-200">{title}</h1>
      <div className="flex items-center gap-4">
        <button onClick={toggleDark} className="text-neutral-400 hover:text-white">
          {darkMode ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <div className="relative text-neutral-400 hover:text-white cursor-pointer">
          <Bell size={16} />
          {unread > 0 && (
            <span className="absolute -top-1.5 -right-1.5 bg-danger text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center">
              {unread}
            </span>
          )}
        </div>
        <button
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className="text-neutral-400 hover:text-white flex items-center gap-1 text-xs"
        >
          <LogOut size={14} /> Sign out
        </button>
      </div>
    </header>
  );
}
