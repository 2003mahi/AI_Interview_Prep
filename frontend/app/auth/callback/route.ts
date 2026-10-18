import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import type { EmailOtpType } from "@supabase/supabase-js";

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const token_hash = requestUrl.searchParams.get("token_hash");
  const type = requestUrl.searchParams.get("type");
  const rawNext = requestUrl.searchParams.get("next");
  const errorParam = requestUrl.searchParams.get("error");
  const errorDescription = requestUrl.searchParams.get("error_description");

  // Determine correct origin supporting Vercel / reverse proxy headers
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") || "https";
  const origin = forwardedHost
    ? `${forwardedProto}://${forwardedHost}`
    : requestUrl.origin;

  // Prevent open redirect vulnerabilities: strictly validate relative path
  let nextCandidate = rawNext;
  if (nextCandidate && (nextCandidate.startsWith("%2F") || nextCandidate.startsWith("%2f"))) {
    try {
      nextCandidate = decodeURIComponent(nextCandidate);
    } catch {
      // ignore decoding error
    }
  }

  let safeNext = "/login?verified=true";
  if (
    nextCandidate &&
    nextCandidate.startsWith("/") &&
    !nextCandidate.startsWith("//") &&
    !nextCandidate.startsWith("/\\") &&
    !nextCandidate.includes(":")
  ) {
    safeNext = nextCandidate;
  } else if (type === "recovery") {
    safeNext = "/reset-password";
  }

  // Handle URL errors passed directly from Supabase
  if (errorParam || errorDescription) {
    const errorMsg = encodeURIComponent(errorDescription || errorParam || "Authentication error");
    const target = safeNext.startsWith("/reset-password")
      ? `/reset-password?error=${errorMsg}`
      : `/login?error=${errorMsg}`;
    return NextResponse.redirect(new URL(target, origin));
  }

  const supabase = await createClient();

  // Handle PKCE code exchange
  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(new URL(safeNext, origin));
    }
  }

  // Handle token_hash verification (OTP email flow)
  if (token_hash && type) {
    const { error } = await supabase.auth.verifyOtp({
      type: type as EmailOtpType,
      token_hash,
    });
    if (!error) {
      return NextResponse.redirect(new URL(safeNext, origin));
    }
  }

  // If this was a reset-password flow and exchange failed/expired
  if (type === "recovery" || safeNext.startsWith("/reset-password")) {
    return NextResponse.redirect(
      new URL("/reset-password?error=Invalid+or+expired+reset+link.+Please+request+a+new+one.", origin)
    );
  }

  // Return the user to login page with error if something went wrong
  return NextResponse.redirect(
    new URL("/login?error=Could+not+verify+email.+Please+try+signing+in+or+request+a+new+link.", origin)
  );
}

