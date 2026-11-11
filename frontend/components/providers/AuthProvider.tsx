"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, AuthUser, onUnauthorized } from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  /** False until the stored session has been checked, so guards don't flash a redirect. */
  ready: boolean;
  /** True when the API could not be reached (as opposed to the user simply not being signed in). */
  serverUnreachable: boolean;
  login: (email: string, password: string, remember: boolean) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [serverUnreachable, setServerUnreachable] = useState(false);

  const logout = useCallback(() => {
    api.logout().catch(() => undefined);
    setUser(null);
  }, []);

  // Restore the session: the HttpOnly cookie is invisible to the page, so ask the API who we are.
  useEffect(() => {
    let cancelled = false;
    try {
      // Drop tokens left in browser storage by earlier versions; the session now lives in an HttpOnly cookie.
      localStorage.removeItem("paytrace.auth.token");
      sessionStorage.removeItem("paytrace.auth.token");
    } catch {
      /* storage unavailable */
    }
    api
      .me()
      .then((u) => !cancelled && setUser(u))
      .catch((err) => {
        // 401/403 just means "not signed in"; anything else means the API itself is down.
        if (!cancelled && !(err instanceof ApiError && (err.status === 401 || err.status === 403))) setServerUnreachable(true);
      })
      .finally(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    onUnauthorized(() => setUser(null));
    return () => onUnauthorized(null);
  }, []);

  const login = useCallback(async (email: string, password: string, remember: boolean) => {
    const res = await api.login(email, password, remember);
    setUser(res.user);
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const res = await api.register(name, email, password);
    setUser(res.user);
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, serverUnreachable, login, register, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
