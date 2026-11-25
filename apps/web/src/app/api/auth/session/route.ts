import { NextRequest, NextResponse } from "next/server";

const endpoint = "/api/auth/session";
const cookieName = "allsafe_refresh";
const maxAge = 12 * 60 * 60;

function reply(status: number, body?: object) {
  const headers = { "Cache-Control": "no-store" };
  return body ? NextResponse.json(body, { status, headers }) : new NextResponse(null, { status, headers });
}

function cookie(request: NextRequest, response: NextResponse, value: string, age: number) {
  response.cookies.set(cookieName, value, {
    httpOnly: true, secure: process.env.VERCEL === "1" || request.nextUrl.protocol === "https:",
    sameSite: "strict", path: endpoint, maxAge: age,
  });
}

function sameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  // Next can canonicalize a loopback or proxy host when creating nextUrl.
  const protocol = process.env.VERCEL === "1" ? "https:" : request.nextUrl.protocol;
  return origin === request.nextUrl.origin || Boolean(host && origin === `${protocol}//${host}`);
}

function authConfig() {
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim().replace(/\/+$/, "");
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!base || !key) return null;
  return { base, key };
}

async function grant(request: NextRequest, type: "password" | "refresh_token", body: object) {
  const config = authConfig();
  if (!config) return reply(503, { message: "Sign-in is temporarily unavailable." });
  try {
    const upstream = await fetch(`${config.base}/auth/v1/token?grant_type=${type}`, {
      method: "POST",
      headers: { apikey: config.key, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    });
    if (!upstream.ok) {
      if ([400, 401, 403, 422].includes(upstream.status)) {
        const denied = reply(401, { message: type === "password" ? "Check your email and password." : "Your session expired." });
        if (type === "refresh_token") cookie(request, denied, "", 0);
        return denied;
      }
      if (upstream.status === 429) return reply(429, { message: "Too many sign-in attempts. Try again shortly." });
      return reply(503, { message: "Sign-in is temporarily unavailable." });
    }
    const result = await upstream.json();
    if (typeof result.refresh_token !== "string" || typeof result.access_token !== "string" ||
        typeof result.user?.id !== "string" || typeof result.user?.email !== "string") {
      return reply(502, { message: "The account service returned an invalid session." });
    }
    const response = reply(200, {
      access_token: result.access_token,
      expires_in: result.expires_in,
      user: { id: result.user.id, email: result.user.email },
    });
    cookie(request, response, result.refresh_token, maxAge);
    return response;
  } catch {
    return reply(503, { message: "Could not reach the account service." });
  }
}

export async function PUT(request: NextRequest) {
  if (!sameOrigin(request)) return reply(403);
  const body = await request.json().catch(() => null);
  if (typeof body?.email !== "string" || body.email.length > 254 || !body.email ||
      typeof body.password !== "string" || body.password.length > 128 || !body.password) {
    return reply(400, { message: "Enter a valid email and password." });
  }
  return grant(request, "password", { email: body.email, password: body.password });
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return reply(403);
  const token = request.cookies.get(cookieName)?.value;
  return token ? grant(request, "refresh_token", { refresh_token: token }) : reply(401);
}

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) return reply(403);
  const result = reply(204);
  cookie(request, result, "", 0);
  const config = authConfig();
  const body = await request.json().catch(() => null);
  if (config && typeof body?.access_token === "string" && body.access_token.length <= 8192) {
    try {
      await fetch(`${config.base}/auth/v1/logout?scope=local`, {
        method: "POST",
        headers: { apikey: config.key, Authorization: `Bearer ${body.access_token}` },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(4000),
      });
    } catch { /* Local logout still removes the session cookie. */ }
  }
  return result;
}
