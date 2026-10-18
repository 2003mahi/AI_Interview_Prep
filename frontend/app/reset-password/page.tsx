"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import type { EmailOtpType } from "@supabase/supabase-js";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [validatingSession, setValidatingSession] = useState(true);

  useEffect(() => {
    const supabase = createClient();

    // 1. Check for URL error parameters
    const urlError = searchParams.get("error_description") || searchParams.get("error");
    if (urlError) {
      setError(decodeURIComponent(urlError));
      setValidatingSession(false);
      return;
    }

    // 2. Handle token_hash verification directly if passed
    const tokenHash = searchParams.get("token_hash");
    const type = searchParams.get("type");
    if (tokenHash && type) {
      supabase.auth
        .verifyOtp({ token_hash: tokenHash, type: type as EmailOtpType })
        .then(({ error: otpErr }) => {
          if (otpErr) {
            setError(otpErr.message);
          }
          setValidatingSession(false);
        });
      return;
    }

    // 3. Handle code exchange directly if passed
    const code = searchParams.get("code");
    if (code) {
      supabase.auth.exchangeCodeForSession(code).then(({ error: codeErr }) => {
        if (codeErr) {
          setError(codeErr.message);
        }
        setValidatingSession(false);
      });
      return;
    }

    // 4. Listen for auth state recovery events (handles client-side hash fragments)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY" || event === "SIGNED_IN") {
        setError(null);
        setValidatingSession(false);
      }
    });

    // 5. Fallback check for existing session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session && !window.location.hash.includes("access_token")) {
        // If no code, no token_hash, no session and no hash, check after brief delay
        setTimeout(() => {
          setValidatingSession(false);
        }, 1000);
      } else {
        setValidatingSession(false);
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [searchParams]);

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 6) {
      setError("Password must be at least 6 characters long.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match. Please re-enter.");
      return;
    }

    setLoading(true);
    const supabase = createClient();

    const { error: updateError } = await supabase.auth.updateUser({
      password: password,
    });

    if (updateError) {
      setError(updateError.message);
      setLoading(false);
      return;
    }

    // Clear session to ensure clean sign-in with newly updated password
    await supabase.auth.signOut();

    setSuccess(true);
    setLoading(false);

    // Automatically navigate to Sign In page after brief celebration
    setTimeout(() => {
      router.push("/login?message=password-updated");
    }, 2500);
  };

  return (
    <div className="w-full max-w-md rounded-xl bg-white p-8 shadow-md">
      <h2 className="mb-2 text-center text-2xl font-bold text-gray-900">Reset Your Password</h2>
      <p className="mb-6 text-center text-sm text-gray-600">
        Enter your new password below to secure and update your account.
      </p>

      {error && (
        <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-600 border border-red-200">
          <p>{error}</p>
          <div className="mt-2 text-xs">
            <Link href="/forgot-password" className="font-semibold text-red-700 underline">
              Request a new reset link
            </Link>
          </div>
        </div>
      )}

      {success ? (
        <div className="space-y-4">
          <div className="rounded bg-green-50 p-4 text-sm text-green-800 border border-green-200 space-y-2">
            <p className="font-semibold">Password updated successfully!</p>
            <p>
              Your new password is now active in Supabase. You can now sign in with your updated credentials.
            </p>
            <p className="text-xs text-green-700">Redirecting to Sign In page...</p>
          </div>
          <div className="text-center">
            <Link
              href="/login?message=password-updated"
              className="inline-block w-full rounded-md bg-blue-600 py-2.5 text-center text-sm font-semibold text-white hover:bg-blue-700"
            >
              Sign In Now
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={handleUpdatePassword} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">New Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
              className="mt-1 w-full rounded-md border border-gray-300 p-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
              placeholder="ENTER the New Pswd"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Confirm New Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              disabled={loading}
              className="mt-1 w-full rounded-md border border-gray-300 p-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
              placeholder="Confirm the pswd once again"
            />
          </div>

          <button
            type="submit"
            disabled={loading || validatingSession}
            className="w-full rounded-md bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Updating password..." : "Update Password"}
          </button>

          <p className="mt-4 text-center text-sm text-gray-600">
            Remembered your credentials?{" "}
            <Link href="/login" className="font-medium text-blue-600 hover:underline">
              Sign In
            </Link>
          </p>
        </form>
      )}
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <Suspense fallback={<div className="text-gray-500">Loading reset screen...</div>}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
