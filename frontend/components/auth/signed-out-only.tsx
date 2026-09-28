"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api/auth";
import { PageLoader } from "@/components/ui/states";

export function SignedOutOnly({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    authApi
      .me()
      .then(() => {
        router.replace("/dashboard");
      })
      .catch(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!ready) return <PageLoader label="Checking your session" />;
  return children;
}
