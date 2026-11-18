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
type BrowserSession = AuthSession & { chartSessionId: string | null };
export type AuthProfile = {
  id: string;
  email: string;
  role: "admin" | "user";
  status: "active" | "paused";
};

type AuthContextValue = {
  session: AuthSession | null;
  chartSessionId: string | null;
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
const CHART_SESSION_CHANNEL = "allsafe-chart-session-v1";
const CHART_SESSION_WAIT_MS = 1500;
const TAB_ID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;

function isTabId(value: unknown): value is string {
  return typeof value === "string" && TAB_ID_PATTERN.test(value);
}

function newTabId(): string | null {
  return globalThis.crypto?.randomUUID?.() ?? null;
}

// The fragment contains an invitation ID only. The browser never sends it in HTTP requests.
export function chartSessionFragment(chartSessionId: string | null): string {
  return isTabId(chartSessionId) ? `#session=${chartSessionId}` : "";
}

function publishTabMessage(channel: BroadcastChannel | null, message: JsonRecord): void {
  try {
    channel?.postMessage(message);
  } catch {
    // Fall back to ordinary chart sign-in if the browser prevents tab messaging.
  }
}

function openSessionChannel(sessionId: string): BroadcastChannel | null {
  try {
    return typeof BroadcastChannel === "undefined"
      ? null
      : new BroadcastChannel(`${CHART_SESSION_CHANNEL}:${sessionId}`);
  } catch {
    // Browsers without tab messaging can still sign in directly on the chart.
    return null;
  }
}

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
  if (/account_paused|disabled|account_suspended/.test(code)) {
    return "This login is paused. Contact the administrator to restore access.";
  }
  if (status >= 500) return "Account verification is temporarily unavailable. Try again soon.";
  if (/paused|disabled|account_suspended/.test(`${code} ${text}`)) {
    return "This login is paused. Contact the administrator to restore access.";
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
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    // Local memory is still cleared even if Supabase logout is temporarily unreachable.
  }
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
      "This login is paused. Contact the administrator to restore access.",
      403,
      true,
    );
  }
  return profile;
}

function recordCustomerLogin(accessToken: string): void {
  // This is an audit side effect, not part of sign-in authorization. A logging
  // outage must not prevent a verified customer from using the account.
  void fetch(`${API_BASE_URL}/api/v1/auth/login-events`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.timeout(5000),
  }).catch(() => {});
}

function parseAuthUser(value: unknown): AuthUser | null {
  const record = asRecord(value);
  if (typeof record?.id !== "string" || typeof record.email !== "string") return null;
  return { id: record.id, email: record.email };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<BrowserSession | null>(null);
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkingTabSession, setCheckingTabSession] = useState(true);
  const authGeneration = useRef(0);
  const verifiedSession = useRef<BrowserSession | null>(null);
  const tabChannel = useRef<BroadcastChannel | null>(null);

  const clearSession = useCallback(() => {
    ++authGeneration.current;
    tabChannel.current?.close();
    tabChannel.current = null;
    verifiedSession.current = null;
    setSession(null);
    setProfile(null);
    setLoading(false);
    setCheckingTabSession(false);
  }, []);

  const establishSession = useCallback((nextSession: BrowserSession, nextProfile: AuthProfile) => {
    verifiedSession.current = nextSession;
    setSession(nextSession);
    setProfile(nextProfile);

    tabChannel.current?.close();
    const sessionId = nextSession.chartSessionId;
    const channel = sessionId ? openSessionChannel(sessionId) : null;
    tabChannel.current = channel;
    channel?.addEventListener("message", (event: MessageEvent<unknown>) => {
      const message = asRecord(event.data);
      if (!message || verifiedSession.current !== nextSession) return;

      if (message.type === "ended") {
        clearSession();
      } else if (message.type === "request" && isTabId(message.requestId)) {
        publishTabMessage(channel, {
          type: "offer",
          requestId: message.requestId,
          accessToken: nextSession.access_token,
          userId: nextSession.user.id,
        });
      }
    });
  }, [clearSession]);

  const endSession = useCallback((current: BrowserSession | null) => {
    if (current) publishTabMessage(tabChannel.current, { type: "ended" });
    clearSession();
    // Revoke upstream in the background so local sign-out does not depend on connectivity.
    if (current) void signOutFromSupabase(current.access_token);
  }, [clearSession]);

  useEffect(() => {
    const chartPath = window.location.pathname;
    const initialHash = window.location.hash;
    const invitation = /^\/chart\/(?:nifty50|banknifty)\/?$/i.test(chartPath)
      ? /^#session=(.+)$/.exec(initialHash)?.[1]
      : undefined;
    const sessionId = isTabId(invitation) ? invitation : null;
    const requestId = sessionId ? newTabId() : null;
    const channel = sessionId && requestId ? openSessionChannel(sessionId) : null;
    const generation = authGeneration.current;
    let disposed = false;
    let answered = false;

    function finishCheck() {
      window.clearTimeout(timer);
      channel?.close();
      answered = true;
      if (disposed) return;
      if (sessionId && window.location.pathname === chartPath && window.location.hash === initialHash) {
        try {
          window.history.replaceState(window.history.state, "", chartPath + window.location.search);
        } catch {
          // Some browser privacy settings restrict replacing the current history entry.
        }
      }
      if (generation === authGeneration.current) setCheckingTabSession(false);
    }

    function onMessage(event: MessageEvent<unknown>) {
      const message = asRecord(event.data);
      if (!message || generation !== authGeneration.current) return;

      if (message.type === "ended") {
        finishCheck();
        clearSession();
        return;
      }

      if (
        message.type !== "offer" || !sessionId || !requestId || answered || verifiedSession.current ||
        message.requestId !== requestId || typeof message.accessToken !== "string" ||
        !message.accessToken || typeof message.userId !== "string" || !message.userId
      ) return;

      answered = true;
      window.clearTimeout(timer);
      const { accessToken, userId } = message;
      // A tab cannot grant access. The account API must verify both the token and its profile.
      void fetchProfile(accessToken, userId)
        .then((nextProfile) => {
          if (!disposed && generation === authGeneration.current && !verifiedSession.current) {
            establishSession({
              access_token: accessToken,
              user: { id: nextProfile.id, email: nextProfile.email },
              chartSessionId: sessionId,
            }, nextProfile);
          }
        })
        .catch(() => {})
        .finally(finishCheck);
    }

    const timer = window.setTimeout(finishCheck, channel ? CHART_SESSION_WAIT_MS : 0);
    channel?.addEventListener("message", onMessage);
    if (channel) publishTabMessage(channel, { type: "request", requestId });

    return () => {
      disposed = true;
      window.clearTimeout(timer);
      channel?.removeEventListener("message", onMessage);
      channel?.close();
      tabChannel.current?.close();
      tabChannel.current = null;
    };
  }, [clearSession, establishSession]);

  const signIn = useCallback(async (email: string, password: string) => {
    requireSupabaseConfig();
    const generation = ++authGeneration.current;
    setCheckingTabSession(false);
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
        signal: AbortSignal.timeout(12000),
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
        const nextProfile = await fetchProfile(accessToken, user.id);
        if (generation !== authGeneration.current) {
          throw new Error("Sign-in was cancelled. Please sign in again.");
        }
        establishSession({ access_token: accessToken, user, chartSessionId: newTabId() }, nextProfile);
        if (nextProfile.role === "user") recordCustomerLogin(accessToken);
      } catch (cause) {
        void signOutFromSupabase(accessToken);
        throw cause;
      }
    } finally {
      if (generation === authGeneration.current) setLoading(false);
    }
  }, [establishSession]);

  const signOut = useCallback(async () => {
    endSession(verifiedSession.current);
  }, [endSession]);

  const changePassword = useCallback(async (password: string) => {
    if (!session) throw new Error("Sign in before changing your password.");
    if (password.length < 8 || password.length > 128) {
      throw new Error("Choose a password between 8 and 128 characters.");
    }
    setLoading(true);
    const generation = authGeneration.current;
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
        signal: AbortSignal.timeout(12000),
      });
      const body = await readJson(response);
      if (!response.ok) {
        if (generation === authGeneration.current && (response.status === 401 || response.status === 403)) {
          endSession(session);
        }
        throw new Error(accessDeniedMessage(body, response.status));
      }
    } finally {
      if (generation === authGeneration.current) setLoading(false);
    }
  }, [endSession, session]);

  const refreshProfile = useCallback(async () => {
    if (!session) {
      setProfile(null);
      return;
    }
    setLoading(true);
    const generation = authGeneration.current;
    try {
      const nextProfile = await fetchProfile(session.access_token, session.user.id);
      if (generation === authGeneration.current) setProfile(nextProfile);
    } catch (cause) {
      if (generation === authGeneration.current && cause instanceof ProfileCheckError && cause.shouldSignOut) {
        endSession(session);
      }
      throw cause;
    } finally {
      if (generation === authGeneration.current) setLoading(false);
    }
  }, [endSession, session]);

  const value = useMemo<AuthContextValue>(
    () => ({
      session, chartSessionId: session?.chartSessionId ?? null, profile,
      loading: loading || checkingTabSession, signIn, signOut, changePassword, refreshProfile,
    }),
    [session, profile, loading, checkingTabSession, signIn, signOut, changePassword, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
