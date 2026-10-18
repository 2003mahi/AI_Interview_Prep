import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  });

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  const { pathname } = request.nextUrl;
  const protectedRoutes = ["/dashboard", "/interview"];
  const isProtected = protectedRoutes.some((route) =>
    pathname.startsWith(route)
  );

  const errorParam = request.nextUrl.searchParams.get("error");
  const errorCode = request.nextUrl.searchParams.get("error_code");
  const errorDescription = request.nextUrl.searchParams.get("error_description");
  const typeParam = request.nextUrl.searchParams.get("type");

  // If Supabase redirects auth errors or recovery to root '/', forward to /reset-password or /login
  if (pathname === "/" && (errorParam || errorCode || typeParam === "recovery")) {
    const isRecovery = typeParam === "recovery" || errorCode === "otp_expired" || (errorDescription && errorDescription.toLowerCase().includes("recovery"));
    const targetUrl = new URL(isRecovery ? "/reset-password" : "/login", request.url);
    if (errorDescription || errorParam) {
      targetUrl.searchParams.set("error", errorDescription || errorParam || "Authentication error");
    }
    return NextResponse.redirect(targetUrl);
  }

  // If Supabase environment variables are missing on Vercel, don't crash with 500
  if (!supabaseUrl || !supabaseKey) {
    if (isProtected) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("redirectedFrom", pathname);
      return NextResponse.redirect(loginUrl);
    }
    return supabaseResponse;
  }

  try {
    const supabase = createServerClient(
      supabaseUrl,
      supabaseKey,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value }) =>
              request.cookies.set(name, value)
            );
            supabaseResponse = NextResponse.next({
              request,
            });
            cookiesToSet.forEach(({ name, value, options }) =>
              supabaseResponse.cookies.set(name, value, options)
            );
          },
        },
      }
    );

    // Refresh auth token
    const {
      data: { user },
    } = await supabase.auth.getUser();

    // Protect dashboard and interview routes
    if (isProtected && !user) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("redirectedFrom", pathname);
      return NextResponse.redirect(loginUrl);
    }
  } catch (error) {
    console.error("Supabase auth middleware error:", error);
  }

  return supabaseResponse;
}
