import { Suspense } from "react";
import MfaForm from "./MfaForm";

export default function MfaPage() {
  return (
    <Suspense
      fallback={
        <div className="h-screen flex items-center justify-center text-neutral-500 text-sm">
          Loading…
        </div>
      }
    >
      <MfaForm />
    </Suspense>
  );
}
