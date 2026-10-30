"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api-client";
import type { Role } from "@/types";
import { Trash2, Ban, CheckCircle2, KeyRound } from "lucide-react";
import clsx from "clsx";

const ROLES: Role[] = ["viewer", "auditor", "engineer", "admin"];

export default function UsersAdminPage() {
  const qc = useQueryClient();
  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: api.admin.listUsers });

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [resetTarget, setResetTarget] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-users"] });

  const createMutation = useMutation({
    mutationFn: () => api.admin.createUser(username, password, role),
    onSuccess: () => { invalidate(); setUsername(""); setPassword(""); },
  });

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) => api.admin.updateUserRole(id, role),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.admin.deleteUser(id),
    onSuccess: invalidate,
  });

  const disableMutation = useMutation({
    mutationFn: (id: string) => api.admin.disableUser(id),
    onSuccess: invalidate,
  });

  const enableMutation = useMutation({
    mutationFn: (id: string) => api.admin.enableUser(id),
    onSuccess: invalidate,
  });

  const resetMutation = useMutation({
    mutationFn: ({ id, newPassword }: { id: string; newPassword: string }) =>
      api.admin.resetPassword(id, newPassword),
    onSuccess: () => { setResetTarget(null); setResetPassword(""); },
  });

  return (
    <AppShell title="User Management">
      <div className="card mb-6">
        <h2 className="text-sm font-medium mb-3">Create user</h2>
        <div className="flex gap-2 flex-wrap">
          <input className="input-field w-48" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input className="input-field w-48" placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <select className="input-field w-40" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <button className="btn-primary" onClick={() => createMutation.mutate()} disabled={!username || !password}>
            Create
          </button>
        </div>
      </div>

      <div className="card">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-neutral-500 text-left border-b border-white/5">
              <th className="py-2">Username</th>
              <th className="py-2">Role</th>
              <th className="py-2">Status</th>
              <th className="py-2">Created</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id} className="border-b border-white/5">
                <td className="py-2 text-neutral-200">{u.username}</td>
                <td className="py-2">
                  <select
                    className="bg-surface border border-white/10 rounded px-2 py-1"
                    value={u.role}
                    onChange={(e) => roleMutation.mutate({ id: u.id, role: e.target.value as Role })}
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="py-2">
                  <span className={clsx("badge", u.is_active ? "bg-ok/20 text-ok" : "bg-danger/20 text-danger")}>
                    {u.is_active ? "active" : "disabled"}
                  </span>
                </td>
                <td className="py-2 text-neutral-500">{new Date(u.created_at).toLocaleDateString()}</td>
                <td className="py-2">
                  <div className="flex items-center gap-2">
                    {u.is_active ? (
                      <button onClick={() => disableMutation.mutate(u.id)} className="text-warn hover:opacity-80" title="Disable user">
                        <Ban size={14} />
                      </button>
                    ) : (
                      <button onClick={() => enableMutation.mutate(u.id)} className="text-ok hover:opacity-80" title="Re-enable user">
                        <CheckCircle2 size={14} />
                      </button>
                    )}
                    <button onClick={() => setResetTarget(u.id)} className="text-neutral-400 hover:opacity-80" title="Reset password">
                      <KeyRound size={14} />
                    </button>
                    <button onClick={() => deleteMutation.mutate(u.id)} className="text-danger hover:opacity-80" title="Delete user">
                      <Trash2 size={14} />
                    </button>
                  </div>
                  {resetTarget === u.id && (
                    <div className="flex items-center gap-2 mt-2">
                      <input
                        className="input-field w-40"
                        type="password"
                        placeholder="New password (min 8 chars)"
                        value={resetPassword}
                        onChange={(e) => setResetPassword(e.target.value)}
                      />
                      <button
                        className="btn-secondary"
                        onClick={() => resetMutation.mutate({ id: u.id, newPassword: resetPassword })}
                        disabled={resetPassword.length < 8}
                      >
                        Set
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
