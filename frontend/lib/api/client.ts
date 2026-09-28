import { env } from "@/lib/config/env";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export type FetchOptions = RequestInit & { silent?: boolean; skipAuthRefresh?: boolean };

type LoadingListener = (count: number) => void;
let pending = 0;
const loadingListeners = new Set<LoadingListener>();

export function subscribeLoading(listener: LoadingListener) {
  loadingListeners.add(listener);
  listener(pending);
  return () => {
    loadingListeners.delete(listener);
  };
}

function beginRequest() {
  pending += 1;
  loadingListeners.forEach((listener) => listener(pending));
}

function endRequest() {
  pending = Math.max(0, pending - 1);
  loadingListeners.forEach((listener) => listener(pending));
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIToken(match.split("=").slice(1).join("=")) : null;
}

function decodeURIToken(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = apiFetch("/auth/refresh", {
      method: "POST",
      silent: true,
      skipAuthRefresh: true,
    })
      .then(() => true)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function isAuthPath(path: string) {
  return (
    path.startsWith("/auth/login") ||
    path.startsWith("/auth/register") ||
    path.startsWith("/auth/refresh") ||
    path.startsWith("/auth/forgot-password") ||
    path.startsWith("/auth/reset-password")
  );
}

export async function apiFetch<T>(path: string, init: FetchOptions = {}): Promise<T> {
  const { silent = false, skipAuthRefresh = false, ...requestInit } = init;
  const headers = new Headers(requestInit.headers);
  if (!headers.has("Content-Type") && requestInit.body) {
    headers.set("Content-Type", "application/json");
  }
  const csrf = readCookie("csrf_token");
  if (csrf && !headers.has("X-CSRF-Token")) {
    headers.set("X-CSRF-Token", csrf);
  }

  if (!silent) beginRequest();
  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...requestInit,
      headers,
      credentials: "include",
    });

    const body = await parseBody(response);
    if (response.status === 401 && !skipAuthRefresh && !isAuthPath(path)) {
      const refreshed = await refreshSession();
      if (refreshed) {
        return apiFetch<T>(path, { ...init, skipAuthRefresh: true });
      }
    }
    if (!response.ok) {
      const error =
        typeof body === "object" && body && "error" in body
          ? (body as { error: { code?: string; message?: string; details?: unknown } }).error
          : null;
      throw new ApiError(
        response.status,
        error?.code ?? "request_failed",
        error?.message ?? "Request failed",
        error?.details,
      );
    }
    return body as T;
  } finally {
    if (!silent) endRequest();
  }
}

export function unwrap<T>(payload: { data: T }): T {
  return payload.data;
}
