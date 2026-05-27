"use client";

import { useCallback, useEffect, useState } from "react";
import { docmgrApi } from "../api";
import type { CollabVersion } from "../types";

export function useVersions(docId: string | null) {
  const [versions, setVersions] = useState<CollabVersion[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    try {
      const list = await docmgrApi.listVersions(docId);
      setVersions(list);
    } catch {
      // handle error
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    load();
  }, [load]);

  const createVersion = useCallback(
    async (summary?: string) => {
      if (!docId) return;
      const version = await docmgrApi.createVersion(docId, summary ? { summary } : undefined);
      setVersions((prev) => [version, ...prev]);
      return version;
    },
    [docId],
  );

  const restoreVersion = useCallback(
    async (version: number) => {
      if (!docId) return;
      const result = await docmgrApi.restoreVersion(docId, version);
      await load();
      return result;
    },
    [docId, load],
  );

  return { versions, loading, createVersion, restoreVersion, reload: load };
}
