"use client";
import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useAuthStore, useUIStore } from "@/lib/store";
import { api } from "@/lib/api-client";
import { ShieldCheck, ShieldOff } from "lucide-react";

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const darkMode = useUIStore((s) => s.darkMode);
  const toggleDark = useUIStore((s) => s.toggleDarkMode);

  const [provisioning, setProvisioning] = useState<{ otpauth_url: string; secret: string } | null>(null);
  const [code, setCode] = useState("");
  const [mfaStatus, setMfaStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function startEnrollment() {
    setBusy(true);
    setMfaStatus(null);
    try {
      const result = await api.auth.provisionMfa();
      setProvisioning(result);
    } catch {
      setMfaStatus("Could not start MFA enrollment. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmEnrollment(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.auth.enableMfa(code);
      setMfaStatus("MFA enabled.");
      setProvisioning(null);
      setCode("");
    } catch {
      setMfaStatus("Invalid code — check your authenticator app and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function turnOffMfa() {
    setBusy(true);
    try {
      await api.auth.disableMfa();
      setMfaStatus("MFA disabled for this account.");
    } catch {
      setMfaStatus("Could not disable MFA.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Settings">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="text-sm font-medium mb-3">Account</h2>
          <div className="text-xs text-neutral-400 space-y-1">
            <div>Username: <span className="text-neutral-200">{user?.username}</span></div>
            <div>Role: <span className="text-neutral-200 uppercase">{user?.role}</span></div>
          </div>
        </div>
        <div className="card">
          <h2 className="text-sm font-medium mb-3">Appearance</h2>
          <div className="flex items-center justify-between text-xs">
            <span>Dark mode</span>
            <button onClick={toggleDark} className="btn-secondary">{darkMode ? "On" : "Off"}</button>
          </div>
        </div>

        <div className="card md:col-span-2">
          <h2 className="text-sm font-medium mb-3 flex items-center gap-2">
            <ShieldCheck size={16} /> Two-factor authentication
          </h2>
          {!provisioning && (
            <div className="flex items-center gap-3">
              <button onClick={startEnrollment} className="btn-primary" disabled={busy}>
                Set up MFA
              </button>
              <button onClick={turnOffMfa} className="btn-secondary flex items-center gap-1" disabled={busy}>
                <ShieldOff size={14} /> Turn off MFA
              </button>
            </div>
          )}

          {provisioning && (
            <form onSubmit={confirmEnrollment} className="space-y-3 max-w-sm">
              <p className="text-xs text-neutral-400">
                Scan this into your authenticator app, or enter the secret manually:
              </p>
              <code className="block bg-surface rounded-lg p-2 text-xs break-all">{provisioning.secret}</code>
              <p className="text-[11px] text-neutral-500 break-all">{provisioning.otpauth_url}</p>
              <input
                className="input-field"
                placeholder="6-digit code from your app"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                maxLength={6}
                inputMode="numeric"
                required
              />
              <button type="submit" className="btn-primary" disabled={busy || code.length !== 6}>
                Confirm and enable
              </button>
            </form>
          )}
          {mfaStatus && <p className="text-xs text-neutral-400 mt-3">{mfaStatus}</p>}
        </div>

        <div className="card md:col-span-2">
          <h2 className="text-sm font-medium mb-3">Deployment</h2>
          <p className="text-xs text-neutral-400">
            This instance is fully self-hosted and air-gapped — no external API keys or telemetry
            endpoints are configured. See the Security Dashboard for live egress verification.
          </p>
        </div>
      </div>
    </AppShell>
  );
}
