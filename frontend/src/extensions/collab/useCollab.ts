"use client";

import { useEffect, useRef, useState } from "react";
import { HocuspocusProvider } from "@hocuspocus/provider";
import * as Y from "yjs";

const COLLAB_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/collab`
    : "ws://localhost:2026/api/collab";

export interface CollabUser {
  name: string;
  color: string;
  clientId: number;
}

export function useCollab(docId: string | null) {
  const [connected, setConnected] = useState(false);
  const [users, setUsers] = useState<CollabUser[]>([]);
  const ydocRef = useRef<Y.Doc | null>(null);
  const providerRef = useRef<HocuspocusProvider | null>(null);

  useEffect(() => {
    if (!docId) return;

    const ydoc = new Y.Doc();
    ydocRef.current = ydoc;

    const provider = new HocuspocusProvider({
      url: COLLAB_URL,
      name: docId,
      document: ydoc,
      onConnect: () => setConnected(true),
      onDisconnect: () => setConnected(false),
      onClose: () => setConnected(false),
    });
    providerRef.current = provider;

    if (provider.awareness) {
      provider.awareness.on("change", () => {
        const userList: CollabUser[] = [];
        provider.awareness!.getStates().forEach((state: any, clientId: number) => {
          if (state.user) {
            userList.push({ name: state.user.name, color: state.user.color, clientId });
          }
        });
        setUsers(userList);
      });
    }

    return () => {
      provider.destroy();
      ydoc.destroy();
      ydocRef.current = null;
      providerRef.current = null;
      setConnected(false);
      setUsers([]);
    };
  }, [docId]);

  return { ydoc: ydocRef.current, provider: providerRef.current, connected, users };
}
