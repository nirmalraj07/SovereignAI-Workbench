"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";

/** Redirects to /login if there is no valid session. Wraps every
 * authenticated page (dashboard, chat, etc.) — public pages (login, mfa)
 * are not wrapped by this component. */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const hydrate = useAuthStore((s) => s.hydrate);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    hydrate();
    setHydrated(true);
  }, [hydrate]);

  useEffect(() => {
    if (hydrated && !token) router.replace("/login");
  }, [hydrated, token, router]);

  if (!hydrated || !token) {
    return (
      <div className="h-screen flex items-center justify-center text-neutral-500 text-sm">
        Loading session…
      </div>
    );
  }

  return <>{children}</>;
}
