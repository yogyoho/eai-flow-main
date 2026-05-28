"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  const providerRef = useRef<HocuspocusProvider | null>(null);

  // Create Y.Doc synchronously so it's available on first render
  const ydoc = useMemo(() => new Y.Doc(), []);

  useEffect(() => {
    if (!docId) return;

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
      providerRef.current = null;
      setConnected(false);
      setUsers([]);
    };
  }, [docId, ydoc]);

  const broadcastEvent = useCallback((event: { type: string; payload: unknown }) => {
    if (providerRef.current?.awareness) {
      providerRef.current.awareness.setLocalStateField("collabEvent", {
        ...event,
        timestamp: Date.now(),
      });
    }
  }, []);

  useEffect(() => {
    if (!providerRef.current?.awareness) return;
    const awareness = providerRef.current.awareness;
    const seenTimestamps = new Map<number, number>();

    const handler = () => {
      awareness.getStates().forEach((state: any, clientId: number) => {
        if (state.collabEvent && clientId !== awareness.clientID) {
          const ts = state.collabEvent.timestamp || 0;
          const lastTs = seenTimestamps.get(clientId) || 0;
          if (ts > lastTs) {
            seenTimestamps.set(clientId, ts);
            window.dispatchEvent(new CustomEvent("collab-event", { detail: state.collabEvent }));
          }
        }
      });
    };
    awareness.on("change", handler);
    return () => {
      awareness.off("change", handler);
    };
  }, [connected]);

  return { ydoc, provider: providerRef.current, connected, users, broadcastEvent };
}
