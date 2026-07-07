"use client"

import { useState, useCallback, useEffect, useRef } from "react";
import { docmgrApi } from "../api";

interface PersonalDocFile {
  name: string; rel_path: string; size: number; mime: string;
  modified_at: string; starred: boolean; shared: boolean;
}
interface PersonalThreadOutput {
  thread_id: string; display_name: string; files: PersonalDocFile[];
}

const PAGE_SIZE = 20;

export function usePersonalOutputs() {
  const [threads, setThreads] = useState<PersonalThreadOutput[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const skipRef = useRef(0);
  const fetchingMoreRef = useRef(false);

  const fetchFirst = useCallback(async () => {
    setLoading(true);
    try {
      const data = await docmgrApi.listPersonalOutputs({ skip: 0, limit: PAGE_SIZE });
      setThreads(data.threads);
      setTotal(data.total);
      setHasMore(data.has_more);
      skipRef.current = data.threads.length;
    } catch (err) {
      console.error("Failed to fetch personal outputs:", err);
    } finally { setLoading(false); }
  }, []);

  const fetchMore = useCallback(async () => {
    // 用 ref 同步拦截并发（onScroll 高频触发，state 异步会导致多次请求堆积卡死）
    if (fetchingMoreRef.current) return;
    if (!hasMore) return;
    fetchingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const data = await docmgrApi.listPersonalOutputs({ skip: skipRef.current, limit: PAGE_SIZE });
      setThreads(prev => {
        const existing = new Set(prev.map(t => t.thread_id));
        const fresh = data.threads.filter(t => !existing.has(t.thread_id));
        skipRef.current += fresh.length;
        return [...prev, ...fresh];
      });
      setHasMore(data.has_more);
    } catch (err) {
      console.error("Failed to load more:", err);
    } finally {
      fetchingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [hasMore]);

  useEffect(() => { fetchFirst(); }, [fetchFirst]);

  const toggleExpand = useCallback((threadId: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      next.has(threadId) ? next.delete(threadId) : next.add(threadId);
      return next;
    });
  }, []);

  const toggleStar = useCallback(async (threadId: string, relPath: string, current: boolean) => {
    setThreads(prev => prev.map(t => t.thread_id === threadId ? {
      ...t, files: t.files.map(f => f.rel_path === relPath ? { ...f, starred: !current } : f),
    } : t));
    try {
      await docmgrApi.togglePersonalStar(threadId, { rel_path: relPath, starred: !current });
    } catch {
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

  return { threads, total, hasMore, loading, loadingMore, expandedKeys, toggleExpand, toggleStar, toggleShare, fetchMore, refresh: fetchFirst };
}
