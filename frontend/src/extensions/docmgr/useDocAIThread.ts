import { useCallback, useEffect, useRef, useState } from "react";

import { resolveSubThreadId } from "./utils/docThread";

const STORAGE_PREFIX = "docmgr-ai-subthread:";

/** Read the CSRF cookie value from document.cookie. */
function readCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = /(?:^|;\s*)csrf_token=([^;]+)/.exec(document.cookie);
  return match ? match[1]! : null;
}

async function createThread(
  metadata: Record<string, unknown>,
): Promise<string> {
  const token = readCsrfToken();
  const resp = await fetch("/api/langgraph/threads", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-CSRF-Token": token } : {}),
    },
    credentials: "include",
    body: JSON.stringify({ metadata }),
  });
  if (!resp.ok) throw new Error(`Thread creation failed: ${resp.status}`);
  const data = await resp.json();
  return data.thread_id as string;
}

/**
 * 校验线程是否仍存在（网关容器重建后 /tmp 临时 checkpoint 清空，localStorage 里的线程 ID 会失效）。
 * 200 = 存在；404 = 已失效（应清除重建）。
 */
async function threadExists(threadId: string): Promise<boolean> {
  const token = readCsrfToken();
  try {
    const resp = await fetch(
      `/api/langgraph/threads/${encodeURIComponent(threadId)}`,
      {
        headers: token ? { "X-CSRF-Token": token } : {},
        credentials: "include",
      },
    );
    return resp.ok;
  } catch {
    // 网络错误不阻断：保守认为存在，避免误删正常线程
    return true;
  }
}

/**
 * Read a previously-saved sub-thread ID for this document from localStorage.
 * Returns null if no mapping exists or if storage is unavailable.
 */
function loadStoredThreadId(parentThreadId: string): string | null {
  try {
    return localStorage.getItem(STORAGE_PREFIX + parentThreadId);
  } catch {
    return null;
  }
}

function saveThreadId(parentThreadId: string, subThreadId: string): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + parentThreadId, subThreadId);
  } catch {
    // storage full or unavailable — ignore, still works in-memory
  }
}

function removeThreadId(parentThreadId: string): void {
  try {
    localStorage.removeItem(STORAGE_PREFIX + parentThreadId);
  } catch {
    // ignore
  }
}

/**
 * 文档 AI 助手子线程懒创建 hook。
 *
 * - 首次打开文档时从 localStorage 恢复已有线程 ID（跨文档切换持久化）
 * - 未找到则创建新线程并保存映射
 * - 支持手动清除（"新对话"按钮）
 */
export function useDocAIThread(parentThreadId: string) {
  const [subThreadId, setSubThreadId] = useState<string | null>(() =>
    loadStoredThreadId(parentThreadId),
  );
  const [isCreating, setIsCreating] = useState(false);
  const creatingRef = useRef(false);
  const lastParentRef = useRef(parentThreadId);

  // Reload stored thread when parentThreadId changes (document switch)
  useEffect(() => {
    if (lastParentRef.current !== parentThreadId) {
      lastParentRef.current = parentThreadId;
      creatingRef.current = false;
      const stored = loadStoredThreadId(parentThreadId);
      setSubThreadId(stored);
    }
  }, [parentThreadId]);

  const ensureThread = useCallback(async (): Promise<string> => {
    // Re-check storage in case this is first call after mount
    let current = subThreadId;
    if (!current) {
      const stored = loadStoredThreadId(parentThreadId);
      if (stored) current = stored;
    }
    if (creatingRef.current)
      throw new Error("Thread creation already in progress");
    creatingRef.current = true;
    setIsCreating(true);
    try {
      const { id, reused } = await resolveSubThreadId({
        storedId: current,
        exists: threadExists,
        create: () =>
          createThread({
            parent_thread_id: parentThreadId,
            type: "docmgr-agent",
            deerflow_sidecar: true,
          }),
      });
      if (!reused) {
        // 原存储 ID 失效或不存在 → 清除旧映射并重建
        console.warn(
          "[useDocAIThread] stored thread missing, recreating:",
          current,
        );
        removeThreadId(parentThreadId);
      }
      setSubThreadId(id);
      saveThreadId(parentThreadId, id);
      return id;
    } finally {
      creatingRef.current = false;
      setIsCreating(false);
    }
  }, [parentThreadId, subThreadId]);

  /** 清除并新建线程 — 用于"新对话"，原子操作保证 subThreadId 永远不过渡到 null */
  const resetThread = useCallback(async () => {
    removeThreadId(parentThreadId);
    creatingRef.current = false;
    try {
      creatingRef.current = true;
      setIsCreating(true);
      const id = await createThread({
        parent_thread_id: parentThreadId,
        type: "docmgr-agent",
        deerflow_sidecar: true,
      });
      setSubThreadId(id);
      saveThreadId(parentThreadId, id);
      console.log("[useDocAIThread] reset: created new thread", id);
    } finally {
      creatingRef.current = false;
      setIsCreating(false);
    }
  }, [parentThreadId]);

  return { subThreadId, ensureThread, isCreating, resetThread };
}
