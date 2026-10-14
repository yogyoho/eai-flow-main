"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";

import { authFetch } from "@/extensions/api/client";
import { cn } from "@/lib/utils";

import { getAssetKbStatus, initializeAssetKb, type AssetKbStatus } from "../api";

interface KbRow {
  id: string;
  name: string;
  translation_enabled: boolean;
  ragflow_dataset_id: string | null;
}

export function SettingsView() {
  const kbQ = useQuery({
    queryKey: ["tlt-settings-kbs"],
    queryFn: async (): Promise<KbRow[]> => {
      const d = await authFetch<{ items: KbRow[] }>("/knowledge-bases");
      return (d.items ?? []).map((x) => ({
        id: x.id,
        name: x.name,
        translation_enabled:
          (x as unknown as Record<string, unknown>).translation_enabled === true,
        ragflow_dataset_id: x.ragflow_dataset_id ?? null,
      }));
    },
  });

  const kbs = kbQ.data ?? [];

  const queryClient = useQueryClient();
  const kbStatusQ = useQuery({
    queryKey: ["tlt-asset-kb-status"],
    queryFn: getAssetKbStatus,
    refetchInterval: 30_000,
  });
  const [initializing, setInitializing] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);
  const st: AssetKbStatus | undefined = kbStatusQ.data;

  const doInitialize = async () => {
    setInitializing(true);
    setInitError(null);
    try {
      await initializeAssetKb();
      await queryClient.invalidateQueries({ queryKey: ["tlt-asset-kb-status"] });
      await queryClient.invalidateQueries({ queryKey: ["tlt-settings-kbs"] });
    } catch (e) {
      setInitError(e instanceof Error ? e.message : String(e));
    } finally {
      setInitializing(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">设置</h1>
        <span className="text-sm text-muted-foreground">知识库翻译开关与运行参数</span>
      </div>

      {/* 检索知识库（B3） */}
      <div className="rounded-lg border">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-xs font-medium text-muted-foreground">检索知识库</span>
          {st && (
            <span className="text-xs">
              {st.state === "ready" && <span className="text-emerald-600">● 已就绪</span>}
              {st.state === "unbound" && <span className="text-muted-foreground">○ 未初始化</span>}
              {st.state === "dangling" && <span className="text-destructive">⚠ 关联失效</span>}
            </span>
          )}
        </div>
        <div className="flex items-center justify-between gap-2 p-3 text-sm">
          <div className="min-w-0">
            {kbStatusQ.isLoading ? (
              <span className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
              </span>
            ) : kbStatusQ.isError ? (
              <span className="text-destructive">
                状态加载失败：{kbStatusQ.error?.message ?? "未知错误"}（需超级管理员）
              </span>
            ) : st?.state === "ready" ? (
              <span className="truncate">
                库名：{st.kb_name} · 已索引：原文 {st.source_count} 篇 · 中文译本 {st.zh_count} 篇
              </span>
            ) : (
              <span className="text-muted-foreground">
                {st?.state === "dangling"
                  ? `关联失效（${st.kb_name}），修复后将重建 dataset（旧库内已索文档需回填）`
                  : "尚未初始化——创建检索知识库后，原文与中文译本将自动入库供 RAG 检索"}
              </span>
            )}
            {initError && <div className="mt-1 text-xs text-destructive">{initError}</div>}
          </div>
          {st && st.state !== "ready" && (
            <button
              onClick={doInitialize}
              disabled={initializing}
              className="shrink-0 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {initializing ? <Loader2 className="mr-1 inline h-3 w-3 animate-spin" /> : null}
              {st.state === "dangling" ? "修复关联" : "初始化"}
            </button>
          )}
        </div>
      </div>

      {/* 知识库翻译开关 */}
      <div className="rounded-lg border">
        <div className="border-b px-3 py-2 text-xs font-medium text-muted-foreground">
          知识库翻译开关
        </div>
        {kbQ.isLoading ? (
          <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2">知识库</th>
                <th className="px-3 py-2">RAGFlow</th>
                <th className="px-3 py-2 text-right">翻译开关</th>
              </tr>
            </thead>
            <tbody>
              {kbs.map((k) => (
                <tr key={k.id} className="border-b last:border-b-0 hover:bg-muted/50">
                  <td className="px-3 py-2 font-medium">{k.name}</td>
                  <td className="px-3 py-2">
                    {k.ragflow_dataset_id ? "已关联" : "未关联"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span
                      className={cn(
                        "inline-flex h-5 w-9 items-center rounded-full border-2 border-transparent transition-colors cursor-pointer",
                        k.translation_enabled ? "bg-primary" : "bg-input",
                        !k.ragflow_dataset_id && "cursor-not-allowed opacity-50",
                      )}
                    >
                      <span
                        className={cn(
                          "block h-4 w-4 rounded-full bg-background shadow transition-transform",
                          k.translation_enabled ? "translate-x-4" : "translate-x-0",
                        )}
                      />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 运行参数（只读） */}
      <div className="rounded-lg border">
        <div className="border-b px-3 py-2 text-xs font-medium text-muted-foreground">
          运行参数（只读）
        </div>
        <div className="grid grid-cols-[140px_1fr] gap-x-2 gap-y-1 p-3 text-sm">
          <span className="text-xs text-muted-foreground">翻译模型</span>
          <span>本地 LLM（config.yaml models 声明）</span>
          <span className="text-xs text-muted-foreground">并发槽位</span>
          <span>2 · 轮询 5s · 基础设施重试 ≤3</span>
        </div>
      </div>

      {/* 质量标准（占位） */}
      <div className="rounded-lg border">
        <div className="border-b px-3 py-2 text-xs font-medium text-muted-foreground">
          质量标准（样例验收闸产出）
        </div>
        <div className="grid grid-cols-[140px_1fr] gap-x-2 gap-y-1 p-3 text-sm">
          <span className="text-xs text-muted-foreground">中文检索准确率</span>
          <span>目标 80%（完成验收测试后确定）</span>
          <span className="text-xs text-muted-foreground">数字准确性</span>
          <span>译文与原文逐字核对 · 100% 一致（硬性标准）</span>
          <span className="text-xs text-muted-foreground">术语与格式</span>
          <span className="text-muted-foreground">标准待验收测试后与客户确认</span>
        </div>
      </div>
    </div>
  );
}
