"use client";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/lib/store";
import { KeyRound } from "lucide-react";

export default function MfaForm() {
  const router = useRouter();
  const params = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const username = params.get("username") || "";
  const password = params.get("password") || "";
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.auth.login(username, password, code);
      setSession(res.access_token);
      router.replace("/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Invalid MFA code");
    } finally {
      setLoading(false);
    }
  }

  if (!username) {
    return (
      <div className="h-screen flex items-center justify-center text-neutral-400 text-sm">
        Missing login context. <a href="/login" className="text-accent ml-1">Return to login</a>
      </div>
    );
  }

  return (
    <div className="h-screen flex items-center justify-center bg-surface">
      <div className="card w-full max-w-sm">
        <div className="flex items-center gap-2 mb-6">
          <KeyRound className="text-accent" size={22} />
          <span className="font-semibold">Two-factor verification</span>
        </div>
        <p className="text-xs text-neutral-400 mb-4">
          Enter the 6-digit code from your authenticator app for <span className="text-neutral-200">{username}</span>.
        </p>
        <form onSubmit={handleVerify} className="space-y-4">
          <label htmlFor="mfa-code" className="sr-only">Authentication code</label>
          <input
            id="mfa-code"
            className="input-field text-center tracking-[0.5em] text-lg"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            maxLength={6}
            inputMode="numeric"
            autoFocus
            required
          />
          {error && <p className="text-danger text-xs">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading || code.length !== 6}>
            {loading ? "Verifying…" : "Verify"}
          </button>
        </form>
      </div>
    </div>
  );
}
