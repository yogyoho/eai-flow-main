"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, setApiIdentity } from "./api";
import type { DemoUser } from "./types";

const STORAGE_KEY = "eai.workflow.user";
const FALLBACK_USER: DemoUser = {
  handler: "u1001",
  name: "张三",
  group: "研发部",
  roles: ["manager"],
  dept: "d01",
};

interface SessionContextValue {
  user: DemoUser;
  users: DemoUser[];
  loading: boolean;
  authMode: string;
  canSwitch: boolean;
  switchUser: (handler: string) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [handler, setHandler] = useState<string>(FALLBACK_USER.handler);

  const meQuery = useQuery({
    queryKey: ["meta", "me"],
    queryFn: api.meta.me,
    staleTime: 30 * 1000,
    retry: false,
  });
  const authMode = meQuery.data?.auth_mode ?? "local";
  // If identity resolution fails we are almost certainly behind EAI auth with
  // no valid session; do not expose the demo identity switcher in that case.
  const canSwitch = !meQuery.isError && authMode !== "eai";

  const usersQuery = useQuery({
    queryKey: ["meta", "users"],
    queryFn: api.meta.users,
    staleTime: 5 * 60 * 1000,
    enabled: canSwitch,
  });

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) setHandler(saved);
  }, []);

  const remoteUser = useMemo<DemoUser | null>(() => {
    const me = meQuery.data;
    if (!me) return null;
    return {
      handler: me.handler,
      name: me.name,
      group: "EAI 统一身份",
      roles: me.roles || [],
      dept: me.dept,
    };
  }, [meQuery.data]);

  const users = useMemo(() => {
    if (!canSwitch && remoteUser) return [remoteUser];
    const list = usersQuery.data || [];
    return list.length ? list : [remoteUser || FALLBACK_USER];
  }, [canSwitch, remoteUser, usersQuery.data]);

  const user = useMemo(
    () =>
      !canSwitch && remoteUser
        ? remoteUser
        : users.find((item) => item.handler === handler) || users[0] || FALLBACK_USER,
    [canSwitch, handler, remoteUser, users],
  );

  const tenant = meQuery.data?.tenant_id || "000000";
  useEffect(() => {
    setApiIdentity({
      id: user.handler,
      roles: (user.roles || []).join(","),
      dept: user.dept || "",
      tenant,
    });
  }, [tenant, user]);

  const switchUser = useCallback(
    (next: string) => {
      if (!canSwitch) return;
      window.localStorage.setItem(STORAGE_KEY, next);
      setHandler(next);
      queryClient.invalidateQueries();
    },
    [canSwitch, queryClient],
  );

  const loading = meQuery.isLoading || (canSwitch && usersQuery.isLoading);
  const value = useMemo(
    () => ({ user, users, loading, authMode, canSwitch, switchUser }),
    [authMode, canSwitch, loading, switchUser, user, users],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
