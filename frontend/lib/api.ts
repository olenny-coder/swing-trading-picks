"use client";

// API client with Bearer-token injection.
//
// Default: same-origin relative requests (""), which is what the single-service
// Render deployment uses — FastAPI serves both the static frontend and /api.
// Set NEXT_PUBLIC_API_BASE only when the frontend is hosted separately.

import type {
  AccuracyResponse,
  MacroDashboard,
  ResearchStatus,
  SettingsResponse,
  SignalDetail,
  SignalListResponse,
  Summary,
  TestConnectionResult,
  UserOut,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

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

async function request<T>(
  path: string,
  options: RequestInit & { silent?: boolean } = {},
): Promise<T> {
  const { silent, ...init } = options;
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    // Token invalid/expired: clear it. Only bounce to the login page for
    // explicit actions — a background probe (e.g. "who am I?") must leave a
    // logged-out visitor on the demo view rather than force a login screen.
    setToken(null);
    if (
      !silent &&
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
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

  me: () => request<UserOut>("/api/auth/me", { silent: true }),

  // --- user management (admin only) -------------------------------------
  listUsers: () => request<UserOut[]>("/api/users"),

  createUser: (body: { username: string; password: string; is_admin?: boolean }) =>
    request<UserOut>("/api/users", { method: "POST", body: JSON.stringify(body) }),

  updateUser: (
    id: number,
    body: { password?: string; is_active?: boolean; is_admin?: boolean },
  ) => request<UserOut>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  deleteUser: (id: number) => request<void>(`/api/users/${id}`, { method: "DELETE" }),

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

  accuracy: (timeframe?: string) =>
    request<AccuracyResponse>(
      `/api/signals/accuracy${timeframe ? `?timeframe=${timeframe}` : ""}`,
    ),

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

  researchStatus: () => request<ResearchStatus>("/api/research/status"),

  runResearch: (body: { limit?: number; force?: boolean; signal_ids?: number[] } = {}) =>
    request<ResearchStatus>("/api/research/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  clearResearch: () => request<ResearchStatus>("/api/research", { method: "DELETE" }),
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
