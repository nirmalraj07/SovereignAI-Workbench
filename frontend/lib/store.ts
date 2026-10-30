"use client";
import { create } from "zustand";
import type { AuthUser, Role } from "@/types";

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  hydrate: () => void;
  setSession: (token: string) => void;
  logout: () => void;
  hasRole: (min: Role) => boolean;
}

const ROLE_RANK: Record<Role, number> = { viewer: 0, auditor: 1, engineer: 2, admin: 3 };

function decodeJwt(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return { username: payload.sub, role: payload.role };
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  hydrate: () => {
    if (typeof window === "undefined") return;
    const token = window.localStorage.getItem("sovereignai_token");
    if (token) {
      const user = decodeJwt(token);
      set({ token, user });
    }
  },
  setSession: (token: string) => {
    const user = decodeJwt(token);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("sovereignai_token", token);
    }
    set({ token, user });
  },
  logout: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("sovereignai_token");
    }
    set({ token: null, user: null });
  },
  hasRole: (min: Role) => {
    const user = get().user;
    if (!user) return false;
    return ROLE_RANK[user.role] >= ROLE_RANK[min];
  },
}));

interface UIState {
  darkMode: boolean;
  toggleDarkMode: () => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  darkMode: true,

  toggleDarkMode: () =>
    set((s) => {
      const next = !s.darkMode;

      if (typeof document !== "undefined") {
        if (next) {
          document.documentElement.classList.add("dark");
        } else {
          document.documentElement.classList.remove("dark");
        }
      }

      return { darkMode: next };
    }),

  sidebarCollapsed: false,
  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));

interface NotificationUIState {
  toasts: { id: string; message: string; level: "info" | "warning" | "error" | "success" }[];
  push: (message: string, level?: "info" | "warning" | "error" | "success") => void;
  dismiss: (id: string) => void;
}

export const useNotificationStore = create<NotificationUIState>((set) => ({
  toasts: [],
  push: (message, level = "info") =>
    set((s) => ({ toasts: [...s.toasts, { id: crypto.randomUUID(), message, level }] })),
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
