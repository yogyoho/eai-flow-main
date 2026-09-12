"use client";

// EAI-CUSTOM (大纲候选只读展示): 线程大纲候选 JSON(candidates/tech_outline.candidates.json)
// 经核心 artifacts 通道(bidMaterialsApi.outline.candidates)只读渲染——确认态/来源包/受管节点/章节→条款挂接。
// 候选确认走 B1 对话协议(无 UI 写通道), 本组件零 mutation; 404(线程未走大纲自拟流程)为常态内联提示而非错误。

import { Loader2, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import {
  ApiError,
  bidMaterialsApi,
  type OutlineCandidatesPayload,
} from "./bid-materials-api";

// 上次查询的线程 ID 持久化键(仅便利回填, 丢失无碍功能)
const THREAD_ID_STORAGE_KEY = "bid-materials:outline-thread-id";

export function OutlineCandidates() {
  const [threadId, setThreadId] = useState("");
  const [payload, setPayload] = useState<OutlineCandidatesPayload | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);
  const [queriedId, setQueriedId] = useState("");

  const fetchCandidates = useCallback(async (rawId: string) => {
    const id = rawId.trim();
    if (!id) return;
    setQueriedId(id);
    setLoading(true);
    try {
      const result = await bidMaterialsApi.outline.candidates(id);
      setPayload(result);
      setNotFound(result === null);
      try {
        localStorage.setItem(THREAD_ID_STORAGE_KEY, id);
      } catch {
        // localStorage 不可用(隐私模式/禁存储)仅降级, 不阻断查询
      }
    } catch (e) {
      // 403(非本线程 owner)给专文案; 其余错误透传 ApiError message
      if (e instanceof ApiError && e.status === 403) {
        toast.error("无权访问该线程");
      } else {
        toast.error(e instanceof Error ? e.message : "查询大纲候选失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // 挂载时回填上次查询的线程 ID 并自动查询; localStorage 访问 try/catch 包容(SSR/隐私模式)
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(THREAD_ID_STORAGE_KEY);
    } catch {
      saved = null;
    }
    if (saved) {
      setThreadId(saved);
      void fetchCandidates(saved);
    }
  }, [fetchCandidates]);

  const hasResult = payload !== null;

  return (
    <div className="space-y-4">
      {/* Header: 线程 ID 查询 */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-foreground text-base font-semibold">大纲候选</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            回看线程的技术卷大纲候选（tech_outline.candidates.json）：确认态 /
            来源包 / 章节→条款挂接，只读。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={threadId}
            placeholder="线程 ID"
            className="w-72 font-mono text-xs"
            onChange={(e) => setThreadId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && threadId.trim())
                void fetchCandidates(threadId);
            }}
          />
          <Button
            size="sm"
            disabled={loading || !threadId.trim()}
            onClick={() => void fetchCandidates(threadId)}
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            查询
          </Button>
        </div>
      </div>

      {/* 404 内联提示（常态: 线程未走大纲自拟流程/零条款跳过分支） */}
      {notFound && (
        <div className="text-muted-foreground border-border rounded-xl border border-dashed px-4 py-10 text-center text-sm">
          该线程未产生大纲候选文件（未走大纲自拟流程）
        </div>
      )}

      {/* 初始态（尚未查询且无历史回填） */}
      {!hasResult && !notFound && !loading && (
        <div className="text-muted-foreground border-border rounded-xl border border-dashed px-4 py-10 text-center text-sm">
          输入线程 ID 查询该线程的大纲候选；上次查询的线程 ID 会自动回填。
        </div>
      )}

      {hasResult && payload && (
        <div className="border-border overflow-hidden rounded-xl border">
          {/* 状态条 */}
          <div className="bg-muted/50 flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">确认态</span>
              <Badge variant={payload.confirmed ? "default" : "outline"}>
                {payload.confirmed ? "已确认" : "未确认"}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">来源包</span>
              <span className="text-foreground font-medium">
                {payload.source_pack ?? "无 / 自由拟"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">受管节点</span>
              <span className="text-foreground font-medium tabular-nums">
                {payload.managed_node_ids.length}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">章节</span>
              <span className="text-foreground font-medium tabular-nums">
                {payload.chapters.length}
              </span>
            </div>
            <span
              className="text-muted-foreground ml-auto max-w-[220px] truncate font-mono text-xs"
              title={queriedId}
            >
              {queriedId}
            </span>
          </div>
          {/* 章节表（只读） */}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-muted-foreground text-left">
                  <th className="px-4 py-3 font-medium">编号</th>
                  <th className="px-4 py-3 font-medium">章标题</th>
                  <th className="px-4 py-3 font-medium">条款</th>
                  <th className="px-4 py-3 font-medium">备注</th>
                </tr>
              </thead>
              <tbody>
                {payload.chapters.map((ch) => (
                  <tr
                    key={ch.no}
                    className="border-border hover:bg-muted/30 border-b transition-colors last:border-b-0"
                  >
                    <td className="text-foreground px-4 py-3 font-medium tabular-nums">
                      {ch.no}
                    </td>
                    <td className="text-foreground px-4 py-3">{ch.title}</td>
                    <td className="px-4 py-3">
                      {ch.clause_ids.length > 0 ? (
                        <span className="text-foreground font-mono text-xs">
                          {ch.clause_ids.join("、")}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">挂接 0 条</span>
                      )}
                    </td>
                    <td className="text-muted-foreground max-w-[260px] px-4 py-3">
                      <span
                        className="line-clamp-2"
                        title={ch.notes ?? undefined}
                      >
                        {ch.notes ?? "—"}
                      </span>
                    </td>
                  </tr>
                ))}
                {payload.chapters.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="text-muted-foreground px-4 py-12 text-center"
                    >
                      候选文件未包含任何章节。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
