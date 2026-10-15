"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Star } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { authFetch } from "@/extensions/api/client";

import { createRagKb, listRagKbs, setRagKbEnabled, type RagKb } from "../api";

import { RagKbDialog } from "./RagKbDialog";

const DEFAULT_KB_KEY = "tlt_default_kb_id";

interface AllKbRow {
  id: string;
  name: string;
  translation_enabled: boolean;
}

export function SettingsView() {
  const queryClient = useQueryClient();
  const ragKbsQ = useQuery({ queryKey: ["tlt-rag-kbs"], queryFn: listRagKbs });
  const allKbsQ = useQuery({
    queryKey: ["tlt-settings-kbs"],
    queryFn: async (): Promise<AllKbRow[]> => {
      // 响应键是 knowledge_bases（KnowledgeBaseListResponse），非 items
      const d = await authFetch<{ knowledge_bases?: AllKbRow[] }>(
        "/knowledge-bases",
      );
      return d.knowledge_bases ?? [];
    },
  });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<RagKb | null>(null);
  const [addingExisting, setAddingExisting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const ragKbs = ragKbsQ.data ?? [];
  const defaultKbId =
    typeof window !== "undefined"
      ? window.localStorage.getItem(DEFAULT_KB_KEY)
      : null;
  const defaultInList = ragKbs.some((k) => k.id === defaultKbId)
    ? defaultKbId
    : null;
  const addable = (allKbsQ.data ?? []).filter(
    (k) => !k.translation_enabled && !ragKbs.some((r) => r.id === k.id),
  );

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["tlt-rag-kbs"] });
    void queryClient.invalidateQueries({ queryKey: ["tlt-settings-kbs"] });
  };

  const doAddExisting = async (kbId: string) => {
    setBusyId(kbId);
    setActionError(null);
    try {
      await setRagKbEnabled(kbId, true);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
      setAddingExisting(false);
    }
  };

  const doRemove = async (kb: RagKb) => {
    setBusyId(kb.id);
    setActionError(null);
    try {
      await setRagKbEnabled(kb.id, false);
      if (defaultKbId === kb.id) window.localStorage.removeItem(DEFAULT_KB_KEY);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const doInitDefault = async () => {
    setBusyId("init");
    setActionError(null);
    try {
      const created = await createRagKb({
        name: "翻译资产库",
        description: "翻译工作台检索知识库（默认）",
        language: "Chinese",
        chunk_method: "naive",
      });
      window.localStorage.setItem(DEFAULT_KB_KEY, created.id);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">设置</h1>
        <span className="text-muted-foreground text-sm">
          RAG 知识库配置与运行参数
        </span>
      </div>

      {/* RAG 知识库配置（多库） */}
      <div className="rounded-lg border">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-muted-foreground text-xs font-medium">
            RAG 知识库配置
          </span>
          <div className="flex items-center gap-2">
            {addable.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="h-7"
                onClick={() => setAddingExisting((v) => !v)}
              >
                添加现有库
              </Button>
            )}
            <Button
              size="sm"
              className="h-7"
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus className="mr-1 h-3.5 w-3.5" /> 新建知识库
            </Button>
          </div>
        </div>

        {/* 添加现有库选单 */}
        {addingExisting && (
          <div className="bg-muted/30 border-b px-3 py-2 text-sm">
            <span className="text-muted-foreground mr-2 text-xs">
              选择要加入翻译体系的库：
            </span>
            <div className="mt-1 flex flex-wrap gap-2">
              {addable.map((k) => (
                <button
                  key={k.id}
                  disabled={busyId === k.id}
                  onClick={() => void doAddExisting(k.id)}
                  className="hover:bg-accent rounded-md border px-2 py-1 text-xs disabled:opacity-50"
                >
                  {busyId === k.id ? (
                    <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />
                  ) : null}
                  {k.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {ragKbsQ.isLoading ? (
          <div className="text-muted-foreground flex items-center gap-2 p-4 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
          </div>
        ) : ragKbs.length === 0 ? (
          <div className="flex items-center justify-between gap-2 p-4 text-sm">
            <span className="text-muted-foreground">
              尚无翻译知识库——可初始化一个默认库（翻译资产库），或新建/添加自定义库。
            </span>
            <Button
              size="sm"
              disabled={busyId === "init"}
              onClick={() => void doInitDefault()}
            >
              {busyId === "init" ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : null}
              初始化默认库
            </Button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                <th className="px-3 py-2">知识库</th>
                <th className="px-3 py-2">语言</th>
                <th className="px-3 py-2">分块·向量</th>
                <th className="px-3 py-2">RAGFlow</th>
                <th className="px-3 py-2 text-right">文档</th>
                <th className="px-3 py-2 text-right">待处理</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {ragKbs.map((k) => (
                <tr
                  key={k.id}
                  className="hover:bg-muted/50 border-b last:border-b-0"
                >
                  <td className="px-3 py-2 font-medium">
                    {defaultInList === k.id && (
                      <Star className="mr-1 inline h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                    )}
                    {k.name}
                  </td>
                  <td className="px-3 py-2">{k.language ?? "—"}</td>
                  <td className="text-muted-foreground px-3 py-2 text-xs">
                    {[k.chunk_method ?? "?", k.embedding_model ?? "?"].join(
                      " · ",
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {k.ragflow_linked ? (
                      <span className="text-emerald-600">已关联 ✓</span>
                    ) : (
                      <span className="text-destructive">未关联</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {k.doc_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {k.pending_count > 0 ? k.pending_count : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {defaultInList !== k.id && (
                        <button
                          className="text-muted-foreground hover:bg-accent hover:text-foreground rounded px-1.5 py-0.5 text-xs"
                          onClick={() => {
                            window.localStorage.setItem(DEFAULT_KB_KEY, k.id);
                            refresh();
                          }}
                        >
                          设为默认
                        </button>
                      )}
                      <button
                        className="text-muted-foreground hover:bg-accent hover:text-foreground rounded px-1.5 py-0.5 text-xs"
                        onClick={() => {
                          setEditing(k);
                          setDialogOpen(true);
                        }}
                      >
                        编辑配置
                      </button>
                      <button
                        disabled={busyId === k.id}
                        className="text-destructive hover:bg-destructive/10 rounded px-1.5 py-0.5 text-xs disabled:opacity-50"
                        onClick={() => void doRemove(k)}
                      >
                        移出
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {actionError && (
          <div className="text-destructive px-3 py-2 text-xs">
            {actionError}
          </div>
        )}
      </div>

      <RagKbDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        onSaved={refresh}
      />

      {/* 运行参数（只读） */}
      <div className="rounded-lg border">
        <div className="text-muted-foreground border-b px-3 py-2 text-xs font-medium">
          运行参数（只读）
        </div>
        <div className="grid grid-cols-[140px_1fr] gap-x-2 gap-y-1 p-3 text-sm">
          <span className="text-muted-foreground text-xs">翻译模型</span>
          <span>本地 LLM（config.yaml models 声明）</span>
          <span className="text-muted-foreground text-xs">并发槽位</span>
          <span>2 · 轮询 5s · 基础设施重试 ≤3</span>
        </div>
      </div>

      {/* 质量标准（占位） */}
      <div className="rounded-lg border">
        <div className="text-muted-foreground border-b px-3 py-2 text-xs font-medium">
          质量标准（样例验收闸产出）
        </div>
        <div className="grid grid-cols-[140px_1fr] gap-x-2 gap-y-1 p-3 text-sm">
          <span className="text-muted-foreground text-xs">中文检索准确率</span>
          <span>目标 80%（完成验收测试后确定）</span>
          <span className="text-muted-foreground text-xs">数字准确性</span>
          <span>译文与原文逐字核对 · 100% 一致（硬性标准）</span>
          <span className="text-muted-foreground text-xs">术语与格式</span>
          <span className="text-muted-foreground">
            标准待验收测试后与客户确认
          </span>
        </div>
      </div>
    </div>
  );
}
