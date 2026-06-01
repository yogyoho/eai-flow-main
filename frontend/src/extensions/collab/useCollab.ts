"use client";

import { HocuspocusProvider } from "@hocuspocus/provider";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as Y from "yjs";

function getCollabUrl(): string {
  if (typeof window === "undefined") {
    return "ws://localhost:8002";
  }

  const configured = process.env.NEXT_PUBLIC_COLLAB_WS_URL;
  if (configured) {
    return configured;
  }

  if (window.location.hostname === "localhost" && window.location.port === "3000") {
    return "ws://localhost:8002";
  }

  return `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/collab`;
}

export interface CollabUser {
  name: string;
  color: string;
  clientId: number;
}

export function useCollab(docId: string | null) {
  const [connected, setConnected] = useState(false);
  const [synced, setSynced] = useState(false);
  const [users, setUsers] = useState<CollabUser[]>([]);
  const providerRef = useRef<HocuspocusProvider | null>(null);

  // Create a separate Y.Doc for each collaborative document.
  const ydoc = useMemo(() => new Y.Doc(), [docId]);

  useEffect(() => {
    if (!docId) return;

    const provider = new HocuspocusProvider({
      url: getCollabUrl(),
      name: docId,
      document: ydoc,
      onConnect: () => setConnected(true),
      onDisconnect: () => { setConnected(false); setSynced(false); },
      onClose: () => { setConnected(false); setSynced(false); },
      onSynced: () => setSynced(true),
    });
    providerRef.current = provider;

    if (provider.awareness) {
      provider.awareness.on("change", () => {
        const userList: CollabUser[] = [];
        provider.awareness!.getStates().forEach((state: Record<string, unknown>, clientId: number) => {
          if (state.user) {
            const user = state.user as { name: string; color: string };
            userList.push({ name: user.name, color: user.color, clientId });
          }
        });
        setUsers(userList);
      });
    }

    return () => {
      provider.destroy();
      providerRef.current = null;
      setConnected(false);
      setSynced(false);
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
      awareness.getStates().forEach((state: Record<string, unknown>, clientId: number) => {
        if (state.collabEvent && clientId !== awareness.clientID) {
          const collabEvent = state.collabEvent as Record<string, unknown>;
          const ts = (collabEvent.timestamp as number) ?? 0;
          const lastTs = seenTimestamps.get(clientId) ?? 0;
          if (ts > lastTs) {
            seenTimestamps.set(clientId, ts);
            window.dispatchEvent(new CustomEvent("collab-event", { detail: collabEvent }));
          }
        }
      });
    };
    awareness.on("change", handler);
    return () => {
      awareness.off("change", handler);
    };
  }, [connected]);

  return { ydoc, provider: providerRef.current, connected, synced, users, broadcastEvent };
}
