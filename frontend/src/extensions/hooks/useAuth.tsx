"use client";

import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

import type { CurrentUser } from "../types";

interface AuthContextType {
  user: CurrentUser | null;
  isLoading: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch("/api/extensions/users/me", { credentials: "include" })
      .then(async (res) => {
        if (res.ok) {
          const u: CurrentUser = await res.json();
          setUser(u);
        }
      })
      .catch(() => {
        // Not authenticated — Gateway Auth will handle the login flow.
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = () => {
    const redirect = encodeURIComponent(
      typeof window !== "undefined" ? window.location.pathname + window.location.search : "/docmgr"
    );
    window.location.href = `/login?redirect=${redirect}`;
  };

  const logout = () => {
    fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" })
      .finally(() => {
        setUser(null);
        window.location.href = "/";
      });
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
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
