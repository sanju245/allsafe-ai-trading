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
import { useRouter } from "next/navigation";
import { fetchApi, AuthApiError } from "@/lib/api";

export interface AppUser {
  id: string;
  username?: string;
  email: string;
  role: "admin" | "user" | "operator" | "auditor" | string;
  is_super_admin?: boolean;
  status: "active" | "paused" | "locked" | string;
  allowed_ip?: string | null;
  permissions?: string[];
  mfa_enabled?: boolean;
  last_login_at?: string | null;
  last_login_ip?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface AuthSession {
  access_token: string;
}

export interface AuthContextValue {
  user: AppUser | null;
  token: string | null;
  session: AuthSession | null;
  csrfToken: string | null;
  loading: boolean;
  error: string | null;
  signIn: (token: string, user: AppUser, csrfToken?: string) => void;
  signOut: (options?: { redirectUrl?: string }) => Promise<void>;
  refreshUser: () => Promise<AppUser | null>;
  clearError: () => void;
}

const STORAGE_KEY = "allsafe_access_token";
const CSRF_STORAGE_KEY = "allsafe_csrf_token";

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readStorageItem(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const value = window.localStorage.getItem(key)?.trim();
    return value || null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(() => readStorageItem(STORAGE_KEY));
  const [csrfToken, setCsrfToken] = useState<string | null>(() => readStorageItem(CSRF_STORAGE_KEY));
  const [user, setUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(false);

  const clearSession = useCallback(() => {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
      window.localStorage.removeItem(CSRF_STORAGE_KEY);
    } catch {
      // Ignore storage clear failures
    }
    setToken(null);
    setCsrfToken(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async (): Promise<AppUser | null> => {
    const currentToken = readStorageItem(STORAGE_KEY);
    if (!currentToken) {
      setUser(null);
      setLoading(false);
      return null;
    }

    try {
      const response = await fetchApi<AppUser>("/api/v1/auth/me", {
        token: currentToken,
      });

      if (isMountedRef.current) {
        setToken(currentToken);
        setUser(response);
        setError(null);
      }
      return response;
    } catch (err) {
      if (!isMountedRef.current) {
        return null;
      }

      if (err instanceof AuthApiError && (err.status === 401 || err.status === 403)) {
        clearSession();
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unable to authenticate session.");
      }

      return null;
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [clearSession]);

  useEffect(() => {
    isMountedRef.current = true;
    void refreshUser();

    return () => {
      isMountedRef.current = false;
    };
  }, [refreshUser]);

  const signIn = useCallback(
    (newToken: string, newUser: AppUser, newCsrfToken?: string) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, newToken);
        if (newCsrfToken) {
          window.localStorage.setItem(CSRF_STORAGE_KEY, newCsrfToken);
        }
      } catch {
        // Continue even if localStorage is blocked
      }
      setToken(newToken);
      if (newCsrfToken) {
        setCsrfToken(newCsrfToken);
      }
      setUser(newUser);
      setError(null);
      setLoading(false);
    },
    [],
  );

  const signOut = useCallback(
    async (options?: { redirectUrl?: string }) => {
      const currentToken = readStorageItem(STORAGE_KEY);
      const currentCsrf = readStorageItem(CSRF_STORAGE_KEY);

      if (currentToken) {
        try {
          await fetchApi("/api/v1/auth/logout", {
            method: "POST",
            token: currentToken,
            csrfToken: currentCsrf,
          });
        } catch {
          // Local session clear remains authoritative if API logout fails
        }
      }

      clearSession();
      router.push(options?.redirectUrl ?? "/login");
      router.refresh();
    },
    [clearSession, router],
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const session = useMemo<AuthSession | null>(
    () => (token ? { access_token: token } : null),
    [token],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      session,
      csrfToken,
      loading,
      error,
      signIn,
      signOut,
      refreshUser,
      clearError,
    }),
    [user, token, session, csrfToken, loading, error, signIn, signOut, refreshUser, clearError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export default AuthProvider;
