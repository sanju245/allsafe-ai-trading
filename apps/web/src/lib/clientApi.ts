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

export function getApiBaseUrl(): string {
  return PUBLIC_API_BASE_URL;
}

export interface ApiErrorPayload {
  detail?: string | { msg?: string }[] | Record<string, unknown>;
  message?: string;
  error?: string;
}

export class AuthApiError extends Error {
  status: number;
  payload?: ApiErrorPayload;

  constructor(message: string, status: number, payload?: ApiErrorPayload) {
    super(message);
    this.name = "AuthApiError";
    this.status = status;
    this.payload = payload;
  }
}

export interface FetchApiOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string | null;
  csrfToken?: string | null;
  body?: string;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  params?: Record<string, string | number | boolean | undefined>;
}

export function buildUrl(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  if (!params) return cleanPath;

  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      searchParams.append(key, String(value));
    }
  }
  const qs = searchParams.toString();
  return qs ? `${cleanPath}?${qs}` : cleanPath;
}

export async function fetchApi<T = unknown>(
  path: string,
  options: FetchApiOptions = {},
): Promise<T> {
  const normalizedPath = buildUrl(path, options.params);
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
    let parsedPayload: ApiErrorPayload | undefined;
    try {
      const errBody: unknown = await response.json();
      if (typeof errBody === "object" && errBody !== null) {
        parsedPayload = errBody as ApiErrorPayload;
        const record = errBody as Record<string, unknown>;
        if (typeof record.detail === "string" && record.detail.trim()) {
          errorMessage = record.detail.trim();
        } else if (Array.isArray(record.detail) && record.detail.length > 0) {
          const first = record.detail[0] as Record<string, unknown> | undefined;
          if (first && typeof first.msg === "string" && first.msg.trim()) {
            errorMessage = first.msg.trim();
          }
        } else if (typeof record.message === "string" && record.message.trim()) {
          errorMessage = record.message.trim();
        } else if (typeof record.error === "string" && record.error.trim()) {
          errorMessage = record.error.trim();
        }
      }
    } catch {
      // Fallback to HTTP status message if response body is not JSON
    }
    throw new AuthApiError(errorMessage, response.status, parsedPayload);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function clientFetch<T = unknown>(
  path: string,
  options: FetchApiOptions = {},
): Promise<T> {
  return fetchApi<T>(path, options);
}

export const clientApi = {
  get: <T = unknown>(path: string, options?: FetchApiOptions) =>
    fetchApi<T>(path, { ...options, method: "GET" }),
  post: <T = unknown>(path: string, body?: unknown, options?: FetchApiOptions) =>
    fetchApi<T>(path, {
      ...options,
      method: "POST",
      body: typeof body === "string" ? body : body !== undefined ? JSON.stringify(body) : undefined,
    }),
  put: <T = unknown>(path: string, body?: unknown, options?: FetchApiOptions) =>
    fetchApi<T>(path, {
      ...options,
      method: "PUT",
      body: typeof body === "string" ? body : body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T = unknown>(path: string, body?: unknown, options?: FetchApiOptions) =>
    fetchApi<T>(path, {
      ...options,
      method: "PATCH",
      body: typeof body === "string" ? body : body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T = unknown>(path: string, options?: FetchApiOptions) =>
    fetchApi<T>(path, { ...options, method: "DELETE" }),
};
