"use client";

import { useCallback, useEffect, useState } from "react";

import { docmgrApi } from "../api";
import type { CollabVersion, VersionDiffResponse } from "../types";

export function useVersions(docId: string | null) {
  const [versions, setVersions] = useState<CollabVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [diffResult, setDiffResult] = useState<VersionDiffResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

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
    void load();
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

  const diffVersions = useCallback(
    async (fromOrVersion: number, toVersion?: number): Promise<void> => {
      if (!docId) return;
      setDiffLoading(true);
      try {
        const to = toVersion ?? (versions.length > 0 && versions[0]!.version !== fromOrVersion ? versions[0]!.version : fromOrVersion);
        const result = await docmgrApi.diffVersions(docId, fromOrVersion, to);
        setDiffResult(result);
      } catch {
        // handle error
      } finally {
        setDiffLoading(false);
      }
    },
    [docId, versions],
  );

  return { versions, loading, createVersion, restoreVersion, reload: load, diffResult, diffLoading, diffVersions };
}
