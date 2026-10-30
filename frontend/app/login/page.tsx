"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/lib/store";
import { ShieldCheck } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.setSession);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.auth.login(username, password);
      setSession(res.access_token);
      router.replace("/dashboard");
    } catch (err: any) {
      if (err?.response?.status === 401 && err?.response?.data?.detail === "MFA code required") {
        router.push(`/mfa?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`);
        return;
      }
      setError(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-screen flex items-center justify-center bg-surface">
      <div className="card w-full max-w-sm">
        <div className="flex items-center gap-2 mb-6">
          <ShieldCheck className="text-accent" size={22} />
          <span className="font-semibold">SovereignAI Workbench</span>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="text-xs text-neutral-400 mb-1 block">Username</label>
            <input
              id="username"
              className="input-field"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label htmlFor="password" className="text-xs text-neutral-400 mb-1 block">Password</label>
            <input
              id="password"
              type="password"
              className="input-field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <p className="text-danger text-xs">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="text-[11px] text-neutral-500 mt-6 text-center">
          On-premise deployment — all authentication happens locally, no external identity provider.
        </p>
      </div>
    </div>
  );
}
