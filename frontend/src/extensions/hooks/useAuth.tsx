"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";

import { authApi, ApiError } from "../api";
import type { CurrentUser, LoginRequest } from "../types";

interface AuthContextType {
  user: CurrentUser | null;
  isLoading: boolean;
  accessToken: string | null;
  login: (data: LoginRequest) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [accessToken, setAccessToken] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    setAccessToken(token);
    if (token) {
      authApi
        .me()
        .then((u) => {
          localStorage.setItem("user_id", u.id);
          setUser(u);
        })
        .catch(() => {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("user_id");
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (data: LoginRequest) => {
    const response = await authApi.login(data);
    localStorage.setItem("access_token", response.access_token);
    localStorage.setItem("refresh_token", response.refresh_token);
    setAccessToken(response.access_token);
    const u = await authApi.me();
    localStorage.setItem("user_id", u.id);
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user_id");
    setAccessToken(null);
    setUser(null);
    if (typeof window !== "undefined") {
      const redirect = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login?redirect=${redirect}`;
    }
  };

  const refreshToken = useCallback(async () => {
    const refresh_token = localStorage.getItem("refresh_token");
    if (!refresh_token) {
      return;
    }
    try {
      const response = await authApi.refresh(refresh_token);
      localStorage.setItem("access_token", response.access_token);
      localStorage.setItem("refresh_token", response.refresh_token);
      setAccessToken(response.access_token);
      const u = await authApi.me();
      localStorage.setItem("user_id", u.id);
    } catch {
      console.warn("Token refresh failed, will retry on next request");
    }
  }, []);

  useEffect(() => {
    const refreshInterval = 50 * 60 * 1000;
    const intervalId = setInterval(() => {
      if (localStorage.getItem("refresh_token")) {
        refreshToken().catch(console.warn);
      }
    }, refreshInterval);

    return () => clearInterval(intervalId);
  }, [refreshToken]);

  return (
    <AuthContext.Provider value={{ user, isLoading, accessToken, login, logout, refreshToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
