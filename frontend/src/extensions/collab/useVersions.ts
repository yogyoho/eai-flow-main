"use client";

import { useCallback, useEffect, useState } from "react";
import { docmgrApi } from "../api";
import type { CollabVersion, VersionDiffResponse } from "../types";

export function useVersions(docId: string | null) {
  const [versions, setVersions] = useState<CollabVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [diffResult, setDiffResult] = useState<VersionDiffResponse | null>(null);

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

  const diffVersions = useCallback(
    async (version: number): Promise<void> => {
      if (!docId) return;
      // Diff against the latest version (first in list) or self if no other versions
      const toVersion = versions.length > 0 && versions[0]!.version !== version ? versions[0]!.version : version;
      const result = await docmgrApi.diffVersions(docId, version, toVersion);
      setDiffResult(result);
    },
    [docId, versions],
  );

  return { versions, loading, createVersion, restoreVersion, reload: load, diffResult, diffVersions };
}
