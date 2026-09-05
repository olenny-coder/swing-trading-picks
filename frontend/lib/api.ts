"use client";

// API client with Bearer-token injection. All requests go through the Next.js
// /api rewrite (same-origin), so no CORS and no backend URL in the bundle.

import type {
  MacroDashboard,
  SettingsResponse,
  SignalDetail,
  SignalListResponse,
  Summary,
  TestConnectionResult,
} from "./types";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("stp_token");
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem("stp_token", token);
  else window.localStorage.removeItem("stp_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    // Token invalid/expired: clear it and redirect to login.
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  dailySignals: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<SignalListResponse>(`/api/signals/daily${suffix}`);
  },

  signals: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<SignalListResponse>(`/api/signals${suffix}`);
  },

  summary: () => request<Summary>("/api/signals/summary"),

  signalDetail: (id: number | string) => request<SignalDetail>(`/api/signals/${id}`),

  macroDashboard: () => request<MacroDashboard>("/api/macro/dashboard"),

  settings: () => request<SettingsResponse>("/api/settings"),

  saveCredential: (provider: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/settings/credentials/${provider}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteCredential: (provider: string) =>
    request<void>(`/api/settings/credentials/${provider}`, { method: "DELETE" }),

  testConnection: (provider: string) =>
    request<TestConnectionResult>("/api/settings/test", {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),

  refreshData: () =>
    request<{ started: boolean; running: boolean; error: string | null }>("/api/refresh", {
      method: "POST",
    }),

  refreshStatus: () =>
    request<RefreshStatus>("/api/refresh/status"),
};

export interface RefreshStatus {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  result: {
    provider: string;
    tickers: number;
    bars: number;
    signal_date: string;
    signals: Record<string, number>;
  } | null;
  error: string | null;
}
