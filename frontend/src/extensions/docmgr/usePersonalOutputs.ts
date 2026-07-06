"use client"

import { useState, useCallback, useEffect } from "react";
import { docmgrApi } from "../api";

interface PersonalDocFile {
  name: string; rel_path: string; size: number; mime: string;
  modified_at: string; starred: boolean; shared: boolean;
}
interface PersonalThreadOutput {
  thread_id: string; display_name: string; files: PersonalDocFile[];
}

export function usePersonalOutputs() {
  const [threads, setThreads] = useState<PersonalThreadOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const fetchOutputs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await docmgrApi.listPersonalOutputs();
      setThreads(data.threads);
    } catch (err) {
      console.error("Failed to fetch personal outputs:", err);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchOutputs(); }, [fetchOutputs]);

  const toggleExpand = useCallback((threadId: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      next.has(threadId) ? next.delete(threadId) : next.add(threadId);
      return next;
    });
  }, []);

  const toggleStar = useCallback(async (threadId: string, relPath: string, current: boolean) => {
    // 乐观更新：即时切换 UI 状态
    setThreads(prev => prev.map(t => t.thread_id === threadId ? {
      ...t, files: t.files.map(f => f.rel_path === relPath ? { ...f, starred: !current } : f),
    } : t));
    try {
      await docmgrApi.togglePersonalStar(threadId, { rel_path: relPath, starred: !current });
    } catch {
      // 失败回滚
      setThreads(prev => prev.map(t => t.thread_id === threadId ? {
        ...t, files: t.files.map(f => f.rel_path === relPath ? { ...f, starred: current } : f),
      } : t));
    }
  }, []);

  const toggleShare = useCallback(async (threadId: string, relPath: string, current: boolean) => {
    setThreads(prev => prev.map(t => t.thread_id === threadId ? {
      ...t, files: t.files.map(f => f.rel_path === relPath ? { ...f, shared: !current } : f),
    } : t));
    try {
      await docmgrApi.togglePersonalShare(threadId, { rel_path: relPath, shared: !current });
    } catch {
      setThreads(prev => prev.map(t => t.thread_id === threadId ? {
        ...t, files: t.files.map(f => f.rel_path === relPath ? { ...f, shared: current } : f),
      } : t));
    }
  }, []);

  return { threads, loading, expandedKeys, toggleExpand, toggleStar, toggleShare, refresh: fetchOutputs };
}
