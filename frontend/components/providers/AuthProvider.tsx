"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, AuthUser, getAuthToken, onUnauthorized, setAuthToken } from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  /** False until the stored session has been checked, so guards don't flash a redirect. */
  ready: boolean;
  login: (email: string, password: string, remember: boolean) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
  }, []);

  // Restore the session: a stored token is only trusted once the API confirms it.
  useEffect(() => {
    let cancelled = false;
    if (!getAuthToken()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then((u) => !cancelled && setUser(u))
      .catch(() => !cancelled && setAuthToken(null))
      .finally(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    onUnauthorized(logout);
    return () => onUnauthorized(null);
  }, [logout]);

  const login = useCallback(async (email: string, password: string, remember: boolean) => {
    const res = await api.login(email, password);
    setAuthToken(res.access_token, remember);
    setUser(res.user);
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const res = await api.register(name, email, password);
    setAuthToken(res.access_token, true);
    setUser(res.user);
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, login, register, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
