import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const rawNext = requestUrl.searchParams.get("next");

  // Determine correct origin supporting Vercel / reverse proxy headers
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") || "https";
  const origin = forwardedHost
    ? `${forwardedProto}://${forwardedHost}`
    : requestUrl.origin;

  // Prevent open redirect vulnerabilities: strictly validate relative path
  // Defaults to login page with verified status
  let safeNext = "/login?verified=true";
  if (
    rawNext &&
    rawNext.startsWith("/") &&
    !rawNext.startsWith("//") &&
    !rawNext.startsWith("/\\") &&
    !rawNext.includes(":")
  ) {
    safeNext = rawNext;
  }

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(new URL(safeNext, origin));
    }
  }

  // Return the user to login page with error if something went wrong
  return NextResponse.redirect(
    new URL("/login?error=Could+not+verify+email.+Please+try+signing+in+or+request+a+new+link.", origin)
  );
}

