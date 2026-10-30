"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/lib/store";

export default function AuthProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const hydrate = useAuthStore((state) => state.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return <>{children}</>;
}