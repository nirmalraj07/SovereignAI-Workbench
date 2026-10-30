"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";

export default function RootPage() {
  const router = useRouter();
  const hydrate = useAuthStore((s) => s.hydrate);
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    router.replace(token ? "/dashboard" : "/login");
  }, [token, router]);

  return null;
}
