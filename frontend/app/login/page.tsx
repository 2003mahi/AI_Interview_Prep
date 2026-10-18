"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const message = searchParams.get("message");
  const verified = searchParams.get("verified");
  const urlError = searchParams.get("error");

  useEffect(() => {
    // If Supabase redirected recovery flow to /login, immediately forward to /reset-password
    if (typeof window !== "undefined" && window.location.hash.includes("type=recovery")) {
      router.push(`/reset-password${window.location.hash}`);
      return;
    }

    const supabase = createClient();
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") {
        router.push("/reset-password");
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { error: authError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (authError) {
      setError(authError.message);
      setLoading(false);
      return;
    }

    router.push("/dashboard");
  };

  return (
    <div className="w-full max-w-md rounded-xl bg-white p-8 shadow-md">
      <h2 className="mb-6 text-center text-2xl font-bold text-gray-900">Sign In to Interview Prep</h2>

      {/* Verification & registration notifications */}
      {message === "check-email" && (
        <div className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700 border border-green-200">
          <p className="font-semibold">Account created!</p>
          <p className="mt-1">Check your email for a verification link! Click it to activate your account.</p>
          <p className="mt-1 text-xs text-green-800">
            Note: Emails from Supabase can take 1-2 minutes or land in your <strong>Spam / Junk</strong> folder.
          </p>
        </div>
      )}

      {verified === "true" && (
        <div className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700 border border-green-200">
          <p className="font-semibold">Email verified successfully!</p>
          <p className="mt-1">Your account is active. Please sign in below to continue.</p>
        </div>
      )}

      {message === "password-updated" && (
        <div className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700 border border-green-200">
          <p className="font-semibold">Password updated successfully!</p>
          <p className="mt-1">Your password has been updated. Please sign in with your new password.</p>
        </div>
      )}

      {(error || urlError) && (
        <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-600 border border-red-200">
          {error || urlError}
        </div>
      )}

      <form onSubmit={handleLogin} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">Email Address</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mt-1 w-full rounded-md border border-gray-300 p-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mt-1 w-full rounded-md border border-gray-300 p-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none"
            placeholder="••••••••"
          />
          <div className="mt-1.5 flex justify-end">
            <Link
              href="/forgot-password"
              className="text-xs font-medium text-blue-600 hover:underline"
            >
              Forgot password?
            </Link>
          </div>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign In"}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-600">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="font-medium text-blue-600 hover:underline">
          Register
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <Suspense fallback={<div className="text-gray-500">Loading...</div>}>
        <LoginForm />
      </Suspense>
    </div>
  );
}

