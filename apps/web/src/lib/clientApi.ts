// Browser-safe API client for communicating with the FastAPI backend.
// Only references public NEXT_PUBLIC_API_BASE_URL; never reads server-only secrets.

export const PUBLIC_API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production"
    ? "https://allsafe-ai-api.onrender.com"
    : "http://localhost:8000")
)
  .trim()
  .replace(/\/+$/, "");

// Backwards-compatible alias for client components importing API_BASE_URL
export const API_BASE_URL = PUBLIC_API_BASE_URL;

export class AuthApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AuthApiError";
    this.status = status;
  }
}

export interface FetchApiOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string | null;
  csrfToken?: string | null;
  body?: string;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export async function fetchApi<T = unknown>(
  path: string,
  options: FetchApiOptions = {},
): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${PUBLIC_API_BASE_URL}${normalizedPath}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers ?? {}),
  };

  if (options.body !== undefined && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (options.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  if (options.csrfToken) {
    headers["X-CSRF-Token"] = options.csrfToken;
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body,
    cache: "no-store",
    credentials: "include",
    signal: options.signal,
  });

  if (!response.ok) {
    let errorMessage = `Request failed with HTTP ${response.status}.`;
    try {
      const errBody: unknown = await response.json();
      if (typeof errBody === "object" && errBody !== null) {
        const record = errBody as Record<string, unknown>;
        if (typeof record.detail === "string" && record.detail.trim()) {
          errorMessage = record.detail.trim();
        } else if (typeof record.message === "string" && record.message.trim()) {
          errorMessage = record.message.trim();
        }
      }
    } catch {
      // Fallback to HTTP status message if response body is not JSON
    }
    throw new AuthApiError(errorMessage, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
