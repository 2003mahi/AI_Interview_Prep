"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export function AuthRedirectListener() {
  const router = useRouter();

  useEffect(() => {
    // Check if recovery token is in the hash
    if (typeof window !== "undefined" && window.location.hash.includes("type=recovery")) {
      router.push(`/reset-password${window.location.hash}`);
      return;
    }

    const supabase = createClient();
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") {
        router.push("/reset-password");
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [router]);

  return null;
}
