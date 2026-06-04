"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

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
      toast.error("加载版本列表失败");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    void load();
  }, [load]);

  const createVersion = useCallback(
    async (summary?: string, generateAiSummary?: boolean, content?: string) => {
      if (!docId) return;
      try {
        const version = await docmgrApi.createVersion(docId, {
          summary: summary ?? null,
          generate_summary: generateAiSummary,
          content: content ?? null,
        });
        setVersions((prev) => [version, ...prev]);
        toast.success("版本已保存");
        return version;
      } catch {
        toast.error("创建版本失败");
        throw new Error("create version failed");
      }
    },
    [docId],
  );

  const restoreVersion = useCallback(
    async (version: number) => {
      if (!docId) return;
      try {
        const result = await docmgrApi.restoreVersion(docId, version);
        await load();
        toast.success("版本已恢复");
        return result;
      } catch {
        toast.error("恢复版本失败");
        throw new Error("restore version failed");
      }
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
        toast.error("加载差异对比失败");
      } finally {
        setDiffLoading(false);
      }
    },
    [docId, versions],
  );

  return { versions, loading, createVersion, restoreVersion, reload: load, diffResult, diffLoading, diffVersions };
}
