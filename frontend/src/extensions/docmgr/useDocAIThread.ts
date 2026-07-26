import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_PREFIX = "docmgr-ai-subthread:";

/** Read the CSRF cookie value from document.cookie. */
function readCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? match[1] : null;
}

async function createThread(metadata: Record<string, unknown>): Promise<string> {
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
  const [subThreadId, setSubThreadId] = useState<string | null>(() => loadStoredThreadId(parentThreadId));
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
    if (!subThreadId) {
      const stored = loadStoredThreadId(parentThreadId);
      if (stored) {
        setSubThreadId(stored);
        return stored;
      }
    }
    if (subThreadId) return subThreadId;
    if (creatingRef.current) throw new Error("Thread creation already in progress");
    creatingRef.current = true;
    setIsCreating(true);
    try {
      const id = await createThread({ parent_thread_id: parentThreadId, type: "docmgr-agent", deerflow_sidecar: true });
      setSubThreadId(id);
      saveThreadId(parentThreadId, id);
      console.log("[useDocAIThread] created thread", id);
      return id;
    } finally {
      creatingRef.current = false;
      setIsCreating(false);
    }
  }, [parentThreadId, subThreadId]);

  /** Clear stored thread — used by "新对话" in the AI panel */
  const resetThread = useCallback(() => {
    removeThreadId(parentThreadId);
    setSubThreadId(null);
    creatingRef.current = false;
  }, [parentThreadId]);

  return { subThreadId, ensureThread, isCreating, resetThread };
}
