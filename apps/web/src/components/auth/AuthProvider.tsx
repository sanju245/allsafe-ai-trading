"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AuthUser = { id: string; email: string };
export type AuthSession = { access_token: string; user: AuthUser };
export type AuthProfile = {
  id: string;
  email: string;
  role: "admin" | "user";
  status: "active" | "paused";
  allowed_ip: string | null;
  client_ip: string;
};

type AuthContextValue = {
  session: AuthSession | null;
  profile: AuthProfile | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  changePassword: (password: string) => Promise<void>;
  refreshProfile: () => Promise<void>;
};

type JsonRecord = Record<string, unknown>;
type ApiAuthReply = {
  access_token?: unknown;
  user?: unknown;
};

const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "")
  .trim()
  .replace(/\/+$/, "");
const SUPABASE_ANON_KEY = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "").trim();
const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production"
    ? "https://allsafe-ai-api.onrender.com"
    : "http://localhost:8000")
)
  .trim()
  .replace(/\/+$/, "");

const AuthContext = createContext<AuthContextValue | null>(null);

class ProfileCheckError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly shouldSignOut: boolean,
  ) {
    super(message);
    this.name = "ProfileCheckError";
  }
}

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonRecord)
    : null;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function errorText(body: unknown, fallback: string): string {
  const record = asRecord(body);
  if (!record) return fallback;
  for (const key of ["msg", "message", "error_description", "error", "detail"]) {
    if (typeof record[key] === "string" && record[key].trim()) {
      return record[key].trim();
    }
  }
  return fallback;
}

function accessDeniedMessage(body: unknown, status: number): string {
  const record = asRecord(body);
  const detail = asRecord(record?.detail);
  const code = [record?.code, record?.reason, record?.error, detail?.code, detail?.reason]
    .filter((value): value is string => typeof value === "string")
    .join(" ")
    .toLowerCase();
  const text = [record?.detail, record?.message, record?.msg, detail?.message, detail?.detail]
    .filter((value): value is string => typeof value === "string")
    .join(" ")
    .toLowerCase();
  const allowedIp =
    (typeof record?.allowed_ip === "string" && record.allowed_ip) ||
    (typeof detail?.allowed_ip === "string" && detail.allowed_ip);
  const clientIp =
    (typeof record?.client_ip === "string" && record.client_ip) ||
    (typeof detail?.client_ip === "string" && detail.client_ip);

  if (/paused|disabled|inactive|account_suspended/.test(`${code} ${text}`)) {
    return "This login is paused. Contact the administrator to restore access.";
  }
  if (/ip|address|allow.?list|network/.test(`${code} ${text}`) || allowedIp) {
    const allowed = allowedIp ? ` The approved IP is ${allowedIp}.` : "";
    const current = clientIp ? ` The current IP is ${clientIp}.` : "";
    return `This login is not allowed from the current IP.${allowed}${current}`;
  }
  if (status === 401) return "The email or password is incorrect, or the sign-in has expired.";
  if (status === 403) return "This login is not allowed to access the account.";
  if (status >= 500) return "Account verification is temporarily unavailable. Try again soon.";
  return "Could not verify this account. Check your connection and try again.";
}

function parseProfile(body: unknown): AuthProfile | null {
  const outer = asRecord(body);
  const nested = asRecord(outer?.profile) ?? outer;
  if (!nested) return null;

  const { id, email, role, status, allowed_ip: allowedIp, client_ip: clientIp } = nested;
  if (
    typeof id !== "string" ||
    typeof email !== "string" ||
    (role !== "admin" && role !== "user") ||
    (status !== "active" && status !== "paused") ||
    (allowedIp !== null && typeof allowedIp !== "string") ||
    typeof clientIp !== "string"
  ) {
    return null;
  }

  return {
    id,
    email,
    role,
    status,
    allowed_ip: allowedIp,
    client_ip: clientIp,
  };
}

function requireSupabaseConfig(): void {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error(
      "Account sign-in is not configured yet. The administrator must set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in the web app settings.",
    );
  }
}

async function signOutFromSupabase(accessToken: string): Promise<void> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return;
  try {
    await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
      method: "POST",
      headers: {
        apikey: SUPABASE_ANON_KEY,
        Authorization: `Bearer ${accessToken}`,
      },
      cache: "no-store",
      credentials: "omit",
    });
  } catch {
    // Local memory is still cleared even if Supabase logout is temporarily unreachable.
  }
}

async function fetchProfile(accessToken: string): Promise<AuthProfile> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
      cache: "no-store",
      credentials: "omit",
    });
  } catch {
    throw new Error("Could not reach the account service. Try again soon.");
  }

  const body = await readJson(response);
  if (!response.ok) {
    throw new ProfileCheckError(
      accessDeniedMessage(body, response.status),
      response.status,
      response.status === 401 || response.status === 403,
    );
  }

  const profile = parseProfile(body);
  if (!profile) {
    throw new ProfileCheckError(
      "The account service returned an unexpected profile. Please contact the administrator.",
      response.status,
      true,
    );
  }
  if (profile.status === "paused") {
    throw new ProfileCheckError(
      "This login is paused. Contact the administrator to restore access.",
      403,
      true,
    );
  }
  return profile;
}

function parseAuthUser(value: unknown): AuthUser | null {
  const record = asRecord(value);
  if (typeof record?.id !== "string" || typeof record.email !== "string") return null;
  return { id: record.id, email: record.email };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [loading, setLoading] = useState(false);

  const signIn = useCallback(async (email: string, password: string) => {
    requireSupabaseConfig();
    setLoading(true);
    try {
      const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
        method: "POST",
        headers: {
          apikey: SUPABASE_ANON_KEY,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ email: email.trim(), password }),
        cache: "no-store",
        credentials: "omit",
      });
      const body = await readJson(response);
      if (!response.ok) {
        throw new Error(errorText(body, "Sign-in failed. Check your email and password."));
      }

      const authReply = asRecord(body) as ApiAuthReply | null;
      const accessToken = authReply?.access_token;
      const user = parseAuthUser(authReply?.user);
      if (typeof accessToken !== "string" || !accessToken || !user) {
        throw new Error("Supabase did not return a valid sign-in session.");
      }

      try {
        const nextProfile = await fetchProfile(accessToken);
        setSession({ access_token: accessToken, user });
        setProfile(nextProfile);
      } catch (cause) {
        await signOutFromSupabase(accessToken);
        throw cause;
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    setLoading(true);
    try {
      if (session) await signOutFromSupabase(session.access_token);
    } finally {
      setSession(null);
      setProfile(null);
      setLoading(false);
    }
  }, [session]);

  const changePassword = useCallback(async (password: string) => {
    if (!session) throw new Error("Sign in before changing your password.");
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/password`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ password }),
        cache: "no-store",
        credentials: "omit",
      });
      const body = await readJson(response);
      if (!response.ok) {
        throw new Error(accessDeniedMessage(body, response.status));
      }
    } finally {
      setLoading(false);
    }
  }, [session]);

  const refreshProfile = useCallback(async () => {
    if (!session) {
      setProfile(null);
      return;
    }
    setLoading(true);
    try {
      setProfile(await fetchProfile(session.access_token));
    } catch (cause) {
      if (cause instanceof ProfileCheckError && cause.shouldSignOut) {
        await signOutFromSupabase(session.access_token);
        setSession(null);
        setProfile(null);
      }
      throw cause;
    } finally {
      setLoading(false);
    }
  }, [session]);

  const value = useMemo<AuthContextValue>(
    () => ({ session, profile, loading, signIn, signOut, changePassword, refreshProfile }),
    [session, profile, loading, signIn, signOut, changePassword, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
