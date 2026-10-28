"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CircleCheck,
  Database,
  Loader2,
  Plus,
  RefreshCw,
  Settings,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { authFetch } from "@/extensions/api/client";
import { cn } from "@/lib/utils";

import {
  createRagKb,
  getTranslationModelSettings,
  listRagKbs,
  setRagKbEnabled,
  updateTranslationModel,
  type RagKb,
} from "../api";

import { PageHeader } from "./PageHeader";
import { RagKbDialog } from "./RagKbDialog";
import { NoteBar, Pill } from "./ui/bits";

const DEFAULT_KB_KEY = "tlt_default_kb_id";

/** 绿色成功 chip：淡绿底 + 浅绿边 + 中绿字；图标亮绿（参考原型“已就绪”）。 */
const GREEN_CHIP =
  "border-[var(--success-100)] bg-[var(--success-50)] text-[var(--success-700)]";

interface AllKbRow {
  id: string;
  name: string;
  translation_enabled: boolean;
}

/** 仅用于展示模型来源标签；未知模型按 config.yaml 处理。 */
function modelKind(name: string | null | undefined): string {
  if (!name) return "系统默认";
  if (name === "gemma-4") return "本地 llama.cpp";
  if (name === "glm-4.1v-flash") return "云端 · 思考模型";
  if (name.startsWith("agnes")) return "云端 · 免费额度";
  if (name.startsWith("deepseek")) return "云端 · JSON 模式";
  return "config.yaml";
}

export function SettingsView() {
  const queryClient = useQueryClient();
  const ragKbsQ = useQuery({ queryKey: ["tlt-rag-kbs"], queryFn: listRagKbs });
  const modelQ = useQuery({
    queryKey: ["tlt-model-settings"],
    queryFn: getTranslationModelSettings,
  });
  const setModelM = useMutation({
    mutationFn: updateTranslationModel,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tlt-model-settings"] });
      toast.success("翻译模型已更新，下一次翻译/重跑生效");
    },
    onError: (e) =>
      toast.error(`保存失败：${e instanceof Error ? e.message : String(e)}`),
  });
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
  const linkedCount = ragKbs.filter((k) => k.ragflow_linked).length;
  const pendingTotal = ragKbs.reduce((sum, k) => sum + k.pending_count, 0);
  const effectiveModel = modelQ.data?.effective ?? null;

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["tlt-rag-kbs"] });
    void queryClient.invalidateQueries({ queryKey: ["tlt-settings-kbs"] });
  };

  const refreshAll = () => {
    refresh();
    void queryClient.invalidateQueries({ queryKey: ["tlt-model-settings"] });
    toast.success("配置已刷新");
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

  /** 知识库列表初始化骨架：列形对齐真实表。 */
  const TableSkeleton = () => (
    <div role="status" aria-label="知识库列表加载中">
      <table className="w-full border-collapse text-left" aria-hidden>
        <thead>
          <tr className="border-border border-b">
            <th className="text-muted-foreground px-3 py-2.5 text-xs font-medium">
              知识库
            </th>
            <th className="text-muted-foreground w-24 px-3 py-2.5 text-xs font-medium">
              语言
            </th>
            <th className="text-muted-foreground px-3 py-2.5 text-xs font-medium">
              分块 · 向量
            </th>
            <th className="text-muted-foreground w-28 px-3 py-2.5 text-xs font-medium">
              RAGFlow
            </th>
            <th className="text-muted-foreground w-16 px-3 py-2.5 text-right text-xs font-medium">
              文档
            </th>
            <th className="text-muted-foreground w-20 px-3 py-2.5 text-right text-xs font-medium">
              待处理
            </th>
            <th className="text-muted-foreground w-52 px-3 py-2.5 text-right text-xs font-medium">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 4 }, (_, i) => (
            <tr
              key={i}
              className="border-b border-[var(--gray-100)] last:border-b-0"
            >
              <td className="px-3 py-2">
                <div
                  className="bg-muted-foreground/15 h-3.5 animate-pulse rounded"
                  style={{ width: 110 + (i % 2) * 30 }}
                />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 h-3 w-14 animate-pulse rounded" />
              </td>
              <td className="px-3 py-2">
                <div
                  className="bg-muted-foreground/15 h-3 animate-pulse rounded"
                  style={{ width: 180 + (i % 3) * 20 }}
                />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 h-5 w-16 animate-pulse rounded-full" />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 ml-auto h-3 w-6 animate-pulse rounded" />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 ml-auto h-3 w-6 animate-pulse rounded" />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 ml-auto h-3 w-20 animate-pulse rounded" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="bg-muted dark:bg-background flex h-full flex-col gap-3 overflow-y-auto px-4 pt-3 pb-4">
      <PageHeader
        title="设置"
        description="翻译模型与 RAG 知识库配置 · 运行参数与质量标准只读"
        icon={<Settings />}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[13px]"
              onClick={refreshAll}
            >
              <RefreshCw className="h-3.5 w-3.5" /> 刷新配置
            </Button>
            <Pill tone="success" className={GREEN_CHIP}>
              <CircleCheck className="h-3.5 w-3.5 text-[var(--success-500)]" />
              已自动保存
            </Pill>
          </>
        }
      />

      {/* ═══ 翻译模型 ═══ */}
      <section className="bg-card border-border shrink-0 overflow-hidden rounded-lg border">
        <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <h2 className="text-foreground text-sm font-semibold">翻译模型</h2>
          <span className="text-muted-foreground text-xs">
            与对话模型独立 · 下一次翻译/重跑生效
          </span>
          <div className="ml-auto flex items-center gap-2">
            {modelQ.data ? (
              <Pill tone="primary">
                当前生效 · {modelQ.data.effective ?? "—"}
              </Pill>
            ) : (
              <Pill tone="gray">
                {modelQ.isLoading ? "加载中…" : "未配置"}
              </Pill>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <span className="text-muted-foreground text-xs whitespace-nowrap">
            翻译模型
          </span>
          {modelQ.isLoading ? (
            <div className="bg-muted h-8 w-80 animate-pulse rounded-md" />
          ) : modelQ.isError ? (
            <span className="text-destructive text-xs">
              模型列表加载失败：{String(modelQ.error)}
            </span>
          ) : (
            <Select
              value={modelQ.data?.setting ?? "__default__"}
              onValueChange={(v) =>
                setModelM.mutate(v === "__default__" ? null : v)
              }
              disabled={setModelM.isPending}
            >
              <SelectTrigger
                size="sm"
                className="w-80 max-w-full text-[13px]"
                aria-label="翻译模型"
              >
                <SelectValue placeholder="选择翻译模型" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__" className="text-[13px]">
                  跟随系统默认（{modelQ.data?.effective ?? "—"}）
                </SelectItem>
                {(modelQ.data?.items ?? []).map((m) => (
                  <SelectItem
                    key={m.name}
                    value={m.name}
                    className="text-[13px]"
                  >
                    {m.display_name || m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {modelQ.data ? (
            <Pill tone="gray">{modelKind(effectiveModel)}</Pill>
          ) : null}
          <Pill tone="info">JSON 模式</Pill>
          <span className="text-muted-foreground ml-auto text-xs">
            选择后立即保存，不阻塞正在运行的任务
          </span>
          {setModelM.isPending ? (
            <Loader2 className="text-muted-foreground h-3.5 w-3.5 animate-spin" />
          ) : null}
        </div>
        <div className="px-4 pb-3">
          <NoteBar>
            翻译 worker 使用此模型；对话页的模型选择不影响翻译任务。思考模型已统一使用
            JSON 模式，避免推理内容混入译文。
          </NoteBar>
        </div>
      </section>

      {/* ═══ RAG 知识库 ═══ */}
      <section className="bg-card border-border shrink-0 overflow-hidden rounded-lg border">
        <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <h2 className="text-foreground text-sm font-semibold">RAG 知识库</h2>
          <span className="text-muted-foreground text-xs">
            翻译体系内的检索库 ·{" "}
            <b className="text-foreground tabular-nums">{ragKbs.length}</b> 个
          </span>
          <div className="ml-auto flex items-center gap-2">
            {addable.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-[13px]"
                onClick={() => setAddingExisting((v) => !v)}
              >
                <Plus className="h-3 w-3" /> 添加现有库
              </Button>
            )}
            <Button
              size="sm"
              className="h-7 text-[13px]"
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus className="h-3 w-3" /> 新建知识库
            </Button>
          </div>
        </div>

        <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
          <span className="border-primary/30 bg-primary/5 text-muted-foreground inline-flex h-[22px] items-center gap-1 rounded-full border px-2.5 text-xs">
            已启用{" "}
            <b className="text-primary font-mono text-[11px] tabular-nums">
              {ragKbs.length}
            </b>
          </span>
          <span className="border-border bg-card text-muted-foreground inline-flex h-[22px] items-center gap-1 rounded-full border px-2.5 text-xs">
            已关联 RAGFlow{" "}
            <b className="text-primary font-mono text-[11px] tabular-nums">
              {linkedCount}
            </b>
          </span>
          <span className="border-border bg-card text-muted-foreground inline-flex h-[22px] items-center gap-1 rounded-full border px-2.5 text-xs">
            待处理任务{" "}
            <b className="text-primary font-mono text-[11px] tabular-nums">
              {pendingTotal}
            </b>
          </span>
          <span className="flex-1" />
          <span className="text-muted-foreground text-xs">
            移出只关闭翻译接入，不删除 RAGFlow 库
          </span>
        </div>

        {/* 添加现有库选单 */}
        {addingExisting && (
          <div className="border-border bg-muted/20 border-b px-4 py-2.5">
            <span className="text-muted-foreground text-xs">
              选择要加入翻译体系的库：
            </span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {addable.map((k) => (
                <button
                  key={k.id}
                  disabled={busyId === k.id}
                  onClick={() => void doAddExisting(k.id)}
                  className="border-border bg-card text-muted-foreground hover:border-primary hover:text-primary inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-[13px] transition-colors disabled:opacity-50"
                >
                  {busyId === k.id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Plus className="h-3 w-3" />
                  )}
                  {k.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {ragKbsQ.isLoading ? (
          <TableSkeleton />
        ) : ragKbs.length === 0 ? (
          <div className="m-4 flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-8 text-center">
            <Database className="text-muted-foreground h-8 w-8" />
            <div>
              <p className="text-foreground text-sm font-medium">
                尚无翻译知识库
              </p>
              <p className="text-muted-foreground mt-1 text-xs">
                初始化默认库「翻译资产库」，或新建/添加自定义库。
              </p>
            </div>
            <Button
              size="sm"
              className="text-[13px]"
              disabled={busyId === "init"}
              onClick={() => void doInitDefault()}
            >
              {busyId === "init" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Database className="h-3.5 w-3.5" />
              )}
              初始化默认库
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-border border-b">
                  <th className="text-muted-foreground px-3 py-2.5 text-xs font-medium">
                    知识库
                  </th>
                  <th className="text-muted-foreground w-24 px-3 py-2.5 text-xs font-medium">
                    语言
                  </th>
                  <th className="text-muted-foreground px-3 py-2.5 text-xs font-medium">
                    分块 · 向量
                  </th>
                  <th className="text-muted-foreground w-28 px-3 py-2.5 text-xs font-medium">
                    RAGFlow
                  </th>
                  <th className="text-muted-foreground w-16 px-3 py-2.5 text-right text-xs font-medium">
                    文档
                  </th>
                  <th className="text-muted-foreground w-20 px-3 py-2.5 text-right text-xs font-medium">
                    待处理
                  </th>
                  <th className="text-muted-foreground w-52 px-3 py-2.5 text-right text-xs font-medium">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {ragKbs.map((k) => (
                  <tr
                    key={k.id}
                    className="hover:bg-muted/40 border-b border-[var(--gray-100)] transition-colors last:border-b-0"
                  >
                    <td className="px-3 py-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span
                          className={cn(
                            "truncate text-[13px] font-medium",
                            /^[\x20-\x7E]*$/.test(k.name) && "font-mono",
                          )}
                        >
                          {k.name}
                        </span>
                        {defaultInList === k.id && (
                          <Pill tone="primary">默认</Pill>
                        )}
                      </div>
                    </td>
                    <td
                      className={cn(
                        "px-3 py-2 text-[13px]",
                        k.language &&
                          /^[\x20-\x7E]*$/.test(k.language) &&
                          "font-mono",
                      )}
                    >
                      {k.language ?? "—"}
                    </td>
                    <td className="text-muted-foreground px-3 py-2 font-mono text-xs">
                      {[k.chunk_method ?? "?", k.embedding_model ?? "?"].join(
                        " · ",
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {k.ragflow_linked ? (
                        <Pill tone="success" className={GREEN_CHIP}>
                          <CircleCheck className="h-3.5 w-3.5 text-[var(--success-500)]" />
                          已关联
                        </Pill>
                      ) : (
                        <Pill tone="error">未关联</Pill>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[13px] tabular-nums">
                      {k.doc_count}
                    </td>
                    <td
                      className={cn(
                        "px-3 py-2 text-right font-mono text-[13px] tabular-nums",
                        k.pending_count > 0 && "text-[var(--warning-900)]",
                      )}
                    >
                      {k.pending_count > 0 ? k.pending_count : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-end gap-1">
                        {defaultInList !== k.id && (
                          <button
                            className="text-muted-foreground hover:bg-muted hover:text-foreground rounded px-1.5 py-0.5 text-[13px] whitespace-nowrap transition-colors"
                            onClick={() => {
                              window.localStorage.setItem(
                                DEFAULT_KB_KEY,
                                k.id,
                              );
                              refresh();
                            }}
                          >
                            设为默认
                          </button>
                        )}
                        <button
                          className="text-muted-foreground hover:bg-muted hover:text-foreground rounded px-1.5 py-0.5 text-[13px] whitespace-nowrap transition-colors"
                          onClick={() => {
                            setEditing(k);
                            setDialogOpen(true);
                          }}
                        >
                          编辑配置
                        </button>
                        <button
                          disabled={busyId === k.id}
                          className="text-destructive hover:bg-destructive/10 rounded px-1.5 py-0.5 text-[13px] whitespace-nowrap transition-colors disabled:opacity-50"
                          onClick={() => void doRemove(k)}
                        >
                          移出
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {addable.length > 0 && (
                  <tr>
                    <td colSpan={7} className="p-0">
                      <button
                        onClick={() => setAddingExisting((v) => !v)}
                        className="border-border text-muted-foreground hover:bg-primary/5 hover:text-primary flex w-full items-center justify-center gap-1.5 border-t border-dashed px-3 py-2.5 text-[13px] transition-colors"
                      >
                        <Plus className="h-3 w-3" />
                        从已有知识库添加（{addable.length} 个可用）
                      </button>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        {actionError && (
          <div className="border-border text-destructive border-t px-4 py-2 text-xs">
            {actionError}
          </div>
        )}
        <div className="border-border text-muted-foreground flex flex-wrap items-center gap-2 border-t px-4 py-2 text-xs">
          <span>默认库用于上传时自动选择；删除 RAGFlow dataset 会断开此接入。</span>
          <span className="flex-1" />
          <span>
            共{" "}
            <b className="text-foreground font-mono tabular-nums">
              {ragKbs.length}
            </b>{" "}
            个库
          </span>
        </div>
      </section>

      {/* ═══ 运行参数 / 质量标准 ═══ */}
      <div className="grid shrink-0 gap-3 lg:grid-cols-2">
        <section className="bg-card border-border flex flex-col overflow-hidden rounded-lg border">
          <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <h2 className="text-foreground text-sm font-semibold">运行参数</h2>
            <span className="text-muted-foreground text-xs">
              只读 · 由运行环境决定
            </span>
            <div className="ml-auto">
              <Pill tone="gray">只读</Pill>
            </div>
          </div>
          <div className="divide-border grid auto-cols-fr grid-flow-col divide-x">
            <div className="flex flex-col gap-0.5 px-4 py-3">
              <span className="text-muted-foreground text-xs">并发槽位</span>
              <span className="text-foreground text-xl font-bold tabular-nums">
                2
              </span>
            </div>
            <div className="flex flex-col gap-0.5 px-4 py-3">
              <span className="text-muted-foreground text-xs">轮询间隔</span>
              <span className="text-foreground text-xl font-bold tabular-nums">
                5<small className="text-muted-foreground ml-1 text-xs font-normal">s</small>
              </span>
            </div>
            <div className="flex flex-col gap-0.5 px-4 py-3">
              <span className="text-muted-foreground text-xs">基础设施重试</span>
              <span className="text-foreground text-xl font-bold tabular-nums">
                ≤3<small className="text-muted-foreground ml-1 text-xs font-normal">次</small>
              </span>
            </div>
          </div>
          <div className="border-border text-muted-foreground mt-auto flex items-center gap-2 border-t px-4 py-2 text-xs">
            <span>由运行环境变量控制</span>
            <span className="flex-1" />
            <span className="font-mono text-[10px]">
              EAI_TRANSLATION_SLOTS · POLL_SECONDS · INFRA_RETRIES
            </span>
          </div>
        </section>

        <section className="bg-card border-border shrink-0 overflow-hidden rounded-lg border">
          <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <h2 className="text-foreground text-sm font-semibold">质量标准</h2>
            <span className="text-muted-foreground text-xs">
              样例验收闸产出
            </span>
            <div className="ml-auto">
              <Pill tone="warn">
                <span className="size-1.5 rounded-full bg-current" />
                待客户确认
              </Pill>
            </div>
          </div>
          <div className="flex flex-col">
            <div className="border-border flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2.5 last:border-b-0">
              <span className="text-muted-foreground w-28 shrink-0 text-xs">
                中文检索准确率
              </span>
              <span className="text-muted-foreground min-w-0 flex-1 text-[13px]">
                目标{" "}
                <b className="text-foreground font-semibold tabular-nums">
                  80%
                </b>
                （完成验收测试后确定）
              </span>
              <Pill tone="gray">待确认</Pill>
            </div>
            <div className="border-border flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2.5 last:border-b-0">
              <span className="text-muted-foreground w-28 shrink-0 text-xs">
                数字准确性
              </span>
              <span className="text-muted-foreground min-w-0 flex-1 text-[13px]">
                译文与原文逐字核对 ·{" "}
                <b className="text-foreground font-semibold tabular-nums">
                  100%
                </b>{" "}
                一致
              </span>
              <Pill tone="success" className={GREEN_CHIP}>
                硬性标准
              </Pill>
            </div>
            <div className="border-border flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2.5 last:border-b-0">
              <span className="text-muted-foreground w-28 shrink-0 text-xs">
                术语与格式
              </span>
              <span className="text-muted-foreground min-w-0 flex-1 text-[13px]">
                标准待验收测试后与客户确认
              </span>
              <Pill tone="gray">待确认</Pill>
            </div>
          </div>
        </section>
      </div>

      <div className="shrink-0">
        <NoteBar>
          所有修改即时保存；翻译模型变更在下一次翻译/重跑时生效。RAG
        知识库与运行参数由翻译管线读取，质量标准由样例验收流程维护。
        </NoteBar>
      </div>

      <RagKbDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        onSaved={refresh}
      />
    </div>
  );
}
