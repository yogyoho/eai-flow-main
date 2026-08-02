// EAI-CUSTOM: 文档 AI 子线程决策纯函数（供 useDocAIThread 单测）。
// 网关容器重建后 /tmp 临时 checkpoint 清空，localStorage 里的线程 ID 会失效 →
// 需要先校验存储的 ID 是否仍存在，失效则重建。核心决策抽成纯函数以便 node 环境单测。

export interface ResolveSubThreadResult {
  id: string;
  /** true = 复用存储的线程；false = 重建了新线程（原 ID 失效或没有存储） */
  reused: boolean;
}

/**
 * 决策：存储的线程 ID 有效则复用，否则新建。
 * @param storedId  从 localStorage 恢复的线程 ID（可能失效）
 * @param exists    校验线程是否还存在（200=存在，404=失效）
 * @param create    新建线程，返回新 ID
 */
export async function resolveSubThreadId(opts: {
  storedId: string | null;
  exists: (id: string) => Promise<boolean>;
  create: () => Promise<string>;
}): Promise<ResolveSubThreadResult> {
  if (opts.storedId && (await opts.exists(opts.storedId))) {
    return { id: opts.storedId, reused: true };
  }
  return { id: await opts.create(), reused: false };
}
