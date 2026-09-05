"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken as persistToken } from "./api";

interface AuthState {
  token: string | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  token: null,
  ready: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setTokenState(getToken());
    setReady(true);
  }, []);

  const login = async (username: string, password: string) => {
    const res = await api.login(username, password);
    persistToken(res.access_token);
    setTokenState(res.access_token);
  };

  const logout = () => {
    persistToken(null);
    setTokenState(null);
  };

  return (
    <AuthContext.Provider value={{ token, ready, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
