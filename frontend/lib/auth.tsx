"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken as persistToken } from "./api";
import type { UserOut } from "./types";

interface AuthState {
  token: string | null;
  /** The signed-in account, or null for a guest (who sees the demo dataset). */
  user: UserOut | null;
  /** True when the account has the admin role (user management, keys, refresh). */
  isAdmin: boolean;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  token: null,
  user: null,
  isAdmin: false,
  ready: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const existing = getToken();
    setTokenState(existing);
    if (!existing) {
      setReady(true);
      return;
    }
    // Probe silently: a stale token must not bounce a guest to /login.
    api
      .me()
      .then(setUser)
      .catch(() => {
        persistToken(null);
        setTokenState(null);
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const login = async (username: string, password: string) => {
    const res = await api.login(username, password);
    persistToken(res.access_token);
    setTokenState(res.access_token);
    try {
      setUser(await api.me());
    } catch {
      setUser(null);
    }
  };

  const logout = () => {
    persistToken(null);
    setTokenState(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ token, user, isAdmin: Boolean(user?.is_admin), ready, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
