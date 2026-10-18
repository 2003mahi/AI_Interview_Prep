"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName,
        },
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (authError) {
      setError(authError.message);
      setLoading(false);
      return;
    }

    // In Supabase, if user already exists with email confirmations enabled, identities is empty []
    if (data.user && (!data.user.identities || data.user.identities.length === 0)) {
      setError("An account with this email already exists. Please Sign In or use Forgot Password to reset your credentials.");
      setLoading(false);
      return;
    }

    setSuccess(true);
    setLoading(false);
  };

  const [resendLoading, setResendLoading] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);

  const handleResend = async () => {
    if (!email) return;
    setResendLoading(true);
    setResendMessage(null);
    const supabase = createClient();
    const { error: resendErr } = await supabase.auth.resend({
      type: "signup",
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    setResendLoading(false);
    if (resendErr) {
      setResendMessage(resendErr.message);
    } else {
      setResendMessage("Verification email resent! Please check your inbox and Spam/Junk folder.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow-md">
        <h2 className="mb-6 text-center text-2xl font-bold text-gray-900">Create Account</h2>
        {error && (
          <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-600 border border-red-200">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700 border border-green-200 space-y-2">
            <p>
              Check your email for a verification link! Click it to activate your account.
            </p>
            <p className="text-xs text-green-800">
              Note: Emails from Supabase can take 1-2 minutes or land in your <strong>Spam / Junk / Promotions</strong> folder. Please check there as well!
            </p>
            <button
              type="button"
              onClick={handleResend}
              disabled={resendLoading}
              className="mt-2 text-xs font-semibold text-green-900 underline hover:text-green-700 disabled:opacity-50"
            >
              {resendLoading ? "Resending..." : "Didn't receive email? Click here to resend"}
            </button>
            {resendMessage && (
              <p className="mt-1 text-xs font-medium text-blue-700">{resendMessage}</p>
            )}
          </div>
        )}
        <form onSubmit={handleRegister} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Full Name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-gray-300 p-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none"
              placeholder="John Doe"
            />
          </div>
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
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Creating account..." : "Sign Up"}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-gray-600">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-blue-600 hover:underline">
            Sign In
          </Link>
        </p>
      </div>
    </div>
  );
}
