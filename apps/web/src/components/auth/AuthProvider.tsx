"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
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
};

type AuthContextValue = {
  session: AuthSession | null;
  profile: AuthProfile | null;
  loading: boolean;
  pauseMessage: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  changePassword: (currentPassword: string, password: string) => Promise<void>;
  refreshProfile: () => Promise<void>;
};

type JsonRecord = Record<string, unknown>;
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
    readonly pauseMessage: string | null = null,
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

const pausedLoginMessage = "This login is paused. Contact the administrator to restore access.";

function accountPauseMessage(body: unknown): string | null {
  const detail = asRecord(asRecord(body)?.detail);
  if (detail?.code !== "account_paused") return null;
  const reason = detail.pause_reason;
  return typeof reason === "string" && reason.trim()
    ? `Your account is paused.\n\nReason from your administrator\n${reason}`
    : pausedLoginMessage;
}

function accessDeniedMessage(body: unknown, status: number): string {
  const pause = status === 403 ? accountPauseMessage(body) : null;
  if (pause) return pause;
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
  if (/account_paused|disabled|account_suspended/.test(code)) {
    return pausedLoginMessage;
  }
  if (status >= 500) return "Account verification is temporarily unavailable. Try again soon.";
  if (/paused|disabled|account_suspended/.test(`${code} ${text}`)) {
    return pausedLoginMessage;
  }
  if (/inactive|not active/.test(`${code} ${text}`)) {
    return "This account is not active. Contact the administrator for help.";
  }
  if (status === 401) return "The email or password is incorrect, or the sign-in has expired.";
  if (status === 403) return "This login is not allowed to access the account.";
  return "Could not verify this account. Check your connection and try again.";
}

function parseProfile(body: unknown): AuthProfile | null {
  const outer = asRecord(body);
  const nested = asRecord(outer?.profile) ?? outer;
  if (!nested) return null;

  const { id, email, role, status } = nested;
  if (
    typeof id !== "string" ||
    typeof email !== "string" ||
    (role !== "admin" && role !== "user") ||
    (status !== "active" && status !== "paused")
  ) {
    return null;
  }

  return {
    id,
    email,
    role,
    status,
  };
}

async function fetchProfile(accessToken: string, expectedUserId: string): Promise<AuthProfile> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
      cache: "no-store",
      credentials: "omit",
      // Allow about a minute for the account API to wake after inactivity.
      signal: AbortSignal.timeout(65000),
    });
  } catch (cause) {
    if (cause && typeof cause === "object" && "name" in cause && cause.name === "TimeoutError") {
      throw new Error("The account service is taking longer than usual to start. Please try signing in again.");
    }
    throw new Error("Could not reach the account service. Try again soon.");
  }

  const body = await readJson(response);
  if (!response.ok) {
    throw new ProfileCheckError(
      accessDeniedMessage(body, response.status),
      response.status,
      response.status === 401 || response.status === 403,
      response.status === 403 ? accountPauseMessage(body) : null,
    );
  }

  const profile = parseProfile(body);
  if (!profile || profile.id !== expectedUserId) {
    throw new ProfileCheckError(
      "The account service returned an unexpected profile. Please contact the administrator.",
      response.status,
      true,
    );
  }
  if (profile.status === "paused") {
    throw new ProfileCheckError(
      pausedLoginMessage,
      403,
      true,
      pausedLoginMessage,
    );
  }
  return profile;
}

function parseAuthUser(value: unknown): AuthUser | null {
  const record = asRecord(value);
  if (typeof record?.id !== "string" || typeof record.email !== "string") return null;
  return { id: record.id, email: record.email };
}

type SessionReply = AuthSession & { expiresAt: number };

const SESSION_PATH = "/api/auth/session";
const SESSION_CHANNEL = "allsafe-auth-state";
const SIGNED_OUT_KEY = "allsafe-signed-out";

function signedOut(): boolean {
  try { return localStorage.getItem(SIGNED_OUT_KEY) === "1"; } catch { return false; }
}

function saveSignedOut(value: boolean) {
  try {
    if (value) localStorage.setItem(SIGNED_OUT_KEY, "1");
    else localStorage.removeItem(SIGNED_OUT_KEY);
  } catch { /* Storage may be unavailable on restricted browsers. */ }
}

function sessionRequest(method: "PUT" | "POST" | "DELETE", payload?: Record<string, string>) {
  const request = () => fetch(SESSION_PATH, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
    credentials: "same-origin",
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  // Keep rotating refresh-cookie writes in order across same-origin tabs.
  return typeof navigator !== "undefined" && navigator.locks ?
    navigator.locks.request(SESSION_CHANNEL, request) : request();
}

class SessionRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function readSession(method: "PUT" | "POST", credentials?: Record<string, string>): Promise<SessionReply> {
  const response = await sessionRequest(method, credentials);
  const body = await readJson(response);
  if (!response.ok) {
    throw new SessionRequestError(errorText(body, "Sign-in is unavailable. Try again shortly."), response.status);
  }
  const data = asRecord(body);
  const user = parseAuthUser(data?.user);
  if (typeof data?.access_token !== "string" || !data.access_token || !user) {
    throw new SessionRequestError("The account service returned an invalid session.", 502);
  }
  const expiresIn = data.expires_in;
  return {
    access_token: data.access_token, user,
    expiresAt: Date.now() + (typeof expiresIn === "number" && expiresIn > 0 ? expiresIn : 3600) * 1000,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionReply | null>(null);
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [pauseMessage, setPauseMessage] = useState<string | null>(null);
  const authGeneration = useRef(0);
  const active = useRef<SessionReply | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);

  const clearSession = useCallback((pause: string | null = null) => {
    ++authGeneration.current;
    active.current = null;
    setSession(null);
    setProfile(null);
    setPauseMessage(pause);
    setLoading(false);
  }, []);

  const establish = useCallback((next: SessionReply, nextProfile: AuthProfile) => {
    active.current = next;
    setSession(next);
    setProfile(nextProfile);
    setPauseMessage(null);
  }, []);

  const endSession = useCallback(async (pause: string | null = null) => {
    const current = active.current;
    saveSignedOut(true);
    channel.current?.postMessage("ended");
    clearSession(pause);
    await sessionRequest("DELETE", current ? { access_token: current.access_token } : undefined).catch(() => {});
  }, [clearSession]);

  useEffect(() => {
    let disposed = false;
    const generation = authGeneration.current;
    try { channel.current = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(SESSION_CHANNEL); }
    catch { channel.current = null; }
    const invalidate = () => clearSession();
    const onStorage = (event: StorageEvent) => {
      if (event.key === SIGNED_OUT_KEY && event.newValue === "1") invalidate();
    };
    channel.current?.addEventListener("message", invalidate);
    window.addEventListener("storage", onStorage);
    const timer = window.setTimeout(async () => {
      try {
        if (!signedOut()) {
          const restored = await readSession("POST");
          const account = await fetchProfile(restored.access_token, restored.user.id);
          if (!disposed && generation === authGeneration.current) establish(restored, account);
        }
      } catch (cause) {
        if (!disposed && generation === authGeneration.current && cause instanceof ProfileCheckError && cause.shouldSignOut) {
          void endSession(cause.pauseMessage);
        }
      } finally {
        if (!disposed && generation === authGeneration.current) setLoading(false);
      }
    }, 0);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      channel.current?.close();
      channel.current = null;
      window.removeEventListener("storage", onStorage);
    };
  }, [clearSession, endSession, establish]);

  useEffect(() => {
    if (!session) return;
    let disposed = false;
    const generation = authGeneration.current;
    let timer: number;
    const refresh = async () => {
      try {
        const renewed = await readSession("POST");
        if (disposed || generation !== authGeneration.current) return;
        if (renewed.user.id !== session.user.id) {
          clearSession();
          return;
        }
        const account = await fetchProfile(renewed.access_token, renewed.user.id);
        if (!disposed && generation === authGeneration.current) establish(renewed, account);
      } catch (cause) {
        if (disposed || generation !== authGeneration.current) return;
        if ((cause instanceof SessionRequestError && cause.status === 401) ||
            (cause instanceof ProfileCheckError && cause.shouldSignOut)) {
          void endSession(cause instanceof ProfileCheckError ? cause.pauseMessage : null);
          return;
        }
        timer = window.setTimeout(refresh, 15000);
      }
    };
    timer = window.setTimeout(refresh, Math.max(5000, session.expiresAt - Date.now() - 60000));
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [clearSession, endSession, establish, session]);

  const signIn = useCallback(async (email: string, password: string) => {
    const generation = ++authGeneration.current;
    setLoading(true);
    setPauseMessage(null);
    try {
      const next = await readSession("PUT", { email: email.trim(), password });
      try {
        const nextProfile = await fetchProfile(next.access_token, next.user.id);
        if (generation !== authGeneration.current) throw new Error("Sign-in was cancelled. Please sign in again.");
        saveSignedOut(false);
        channel.current?.postMessage("changed");
        establish(next, nextProfile);
      } catch (cause) {
        if (generation === authGeneration.current) {
          void sessionRequest("DELETE", { access_token: next.access_token }).catch(() => {});
          clearSession(cause instanceof ProfileCheckError ? cause.pauseMessage : null);
        }
        throw cause;
      }
    } finally {
      if (generation === authGeneration.current) setLoading(false);
    }
  }, [clearSession, establish]);

  const changePassword = useCallback(async (currentPassword: string, password: string) => {
    if (!session) throw new Error("Sign in before changing your password.");
    if (password.length < 8 || password.length > 128) throw new Error("Choose a password between 8 and 128 characters.");
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/password`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ current_password: currentPassword, password }),
      cache: "no-store",
      credentials: "omit",
      signal: AbortSignal.timeout(24000),
    });
    if (!response.ok) {
      const body = await readJson(response);
      if (active.current === session && [401, 403].includes(response.status)) {
        void endSession(response.status === 403 ? accountPauseMessage(body) : null);
      }
      if (response.status === 422) {
        throw new Error(errorText(body, "Check your current password and choose a new password."));
      }
      throw new Error(accessDeniedMessage(body, response.status));
    }
  }, [endSession, session]);

  const refreshProfile = useCallback(async () => {
    if (!session) return;
    const generation = authGeneration.current;
    try {
      const next = await fetchProfile(session.access_token, session.user.id);
      if (generation === authGeneration.current) setProfile(next);
    } catch (cause) {
      if (generation === authGeneration.current && cause instanceof ProfileCheckError && cause.shouldSignOut) {
        void endSession(cause.pauseMessage);
      }
      throw cause;
    }
  }, [endSession, session]);

  const value = useMemo<AuthContextValue>(() => ({
    session, profile, loading, pauseMessage, signIn, signOut: endSession, changePassword, refreshProfile,
  }), [session, profile, loading, pauseMessage, signIn, endSession, changePassword, refreshProfile]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
