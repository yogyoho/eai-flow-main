"use client";

/** 配置页 v3: seed 规则库(主) + 定时任务 + 聚类高级参数(折叠)。
 *  移除: 解析模式(v2 已废弃单一 OCR 路径)与货物表名关键字(被 seed 库取代)。
 *  dirty 跟踪 + 保存 clamp + toast 自动消隐。 */

import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  Loader2,
  PackageSearch,
  Save,
  Settings,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetch } from "@/core/api/fetcher";
import { EvolutionCandidatesCard } from "@/extensions/contract-price/components/EvolutionCandidatesCard";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import {
  RAGFLOW_DATASETS,
  type RagflowPhase,
  ragflowPhase,
} from "@/extensions/contract-price/components/ragflowPhase";
import { SeedRulesCard } from "@/extensions/contract-price/components/SeedRulesCard";
import {
  useConfig,
  useContractRagflowStatus,
  useInitContractRagflow,
  useUpdateConfig,
} from "@/extensions/contract-price/hooks";
import type {
  CpaConfig,
  RagflowDatasetStatus,
} from "@/extensions/contract-price/types";
import { cn } from "@/lib/utils";

/** 系统级 OCR 服务注册表(/settings 基础配置维护,api_key 已掩码——此处只消费服务名)。 */
function useOcrServiceNames() {
  return useQuery({
    queryKey: ["cpa", "ocr-service-names"],
    queryFn: async () => {
      const res = await fetch("/api/extensions/ocr/services", {
        credentials: "include",
      });
      if (!res.ok) return [] as string[];
      const data = await res.json();
      return ((data?.services ?? []) as { name: string }[])
        .map((s) => s.name)
        .filter(Boolean);
    },
    staleTime: 60_000,
  });
}

const clamp = (v: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, v));

// ── RAGFlow SSO 知识库连通徽标 + 幂等初始化(页头 actions 槽) ──
// EAI-CUSTOM: 交互态复制自用户确认原型(cpa-settings-ragflow-header.html)——
// pending 查询中(中性) / idle 未初始化(琥珀) / initializing 初始化中(琥珀脉冲) /
// ok 已连接(绿) / partial 部分连接(绿) / err 不可达(红);徽标点击展开两库明细
// 浮层,按钮按态切换 初始化/重试/重新对齐。态推导见 ragflowPhase.ts。

const BADGE_TONE: Record<RagflowPhase, string> = {
  pending: "border-border bg-muted/40 text-muted-foreground",
  idle: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  initializing:
    "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  ok: "border-success/30 bg-success/10 text-success",
  partial: "border-success/30 bg-success/10 text-success",
  err: "border-destructive/30 bg-destructive/10 text-destructive",
};

const BADGE_DOT: Record<RagflowPhase, string> = {
  pending: "bg-muted-foreground/60",
  idle: "bg-amber-500",
  initializing: "bg-amber-500 animate-pulse",
  ok: "bg-success",
  partial: "bg-success",
  err: "bg-destructive",
};

const BADGE_TEXT: Record<RagflowPhase, string> = {
  pending: "RAG知识库 状态…",
  idle: "RAG知识库 未初始化",
  initializing: "RAG知识库 初始化中…",
  ok: "RAG知识库 已连接",
  partial: "RAG知识库 部分连接",
  err: "RAG知识库 不可达",
};

const CONN_LABEL: Record<RagflowPhase, string> = {
  pending: "查询中",
  idle: "—",
  initializing: "连接中",
  ok: "已连接",
  partial: "部分连接",
  err: "不可达",
};

const BUTTON_LABEL: Record<RagflowPhase, string> = {
  pending: "初始化知识库",
  idle: "初始化知识库",
  initializing: "初始化中…",
  ok: "重新对齐",
  partial: "重新对齐",
  err: "重试连接",
};

/** 明细行: 色点 + 右对齐 meta(已连接附带 文档/分块 计数,0 分块省略)。 */
function ragflowRow(phase: RagflowPhase, ds?: RagflowDatasetStatus) {
  if (phase === "pending")
    return { dot: "bg-muted-foreground/60", meta: "查询中…" };
  if (phase === "initializing") return { dot: "bg-amber-500", meta: "创建中…" };
  if (ds?.status === "connected") {
    let meta = "已连接";
    if (ds.document_count !== undefined) meta += ` · ${ds.document_count} 文档`;
    if (ds.chunk_count) meta += ` · ${ds.chunk_count} 分块`;
    return { dot: "bg-success", meta };
  }
  if (phase === "err") return { dot: "bg-muted-foreground/60", meta: "未知" };
  return { dot: "bg-muted-foreground/60", meta: "未创建" };
}

/** ISO → "YYYY-MM-DD HH:mm"(本地时区);缺失/无效返回 null。 */
function formatInitializedAt(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function RagflowHeaderActions() {
  const status = useContractRagflowStatus();
  const init = useInitContractRagflow();
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    if (init.isError && init.error) {
      toast.error(`RAGFlow 初始化失败：${init.error.message}`);
    }
  }, [init.isError, init.error]);

  // pending 是组件级关注点(状态查询进行中,断言任何状态都是谎报)
  const phase: RagflowPhase =
    status.isPending && !status.isError
      ? "pending"
      : ragflowPhase(status, init.isPending);
  const initializedAt = formatInitializedAt(status.data?.initialized_at);
  const footer =
    phase === "pending"
      ? "正在获取 RAGFlow 状态…"
      : phase === "idle"
        ? "点击「初始化知识库」创建并连通"
        : phase === "initializing"
          ? "正在创建合同知识库与合同货物分项表格…"
          : phase === "ok" || phase === "partial"
            ? initializedAt
              ? `初始化于 ${initializedAt} · 幂等:重复点击仅对齐`
              : "幂等:重复点击仅对齐"
            : (status.data?.error ??
              "无法连接 RAGFlow(9380)——请确认 ragflow 容器运行中");

  return (
    <>
      <Popover open={detailOpen} onOpenChange={setDetailOpen}>
        <PopoverTrigger
          aria-label={`RAGFlow 连通状态：${BADGE_TEXT[phase]}`}
          className={cn(
            "group inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-[5px] text-[12.5px] font-medium whitespace-nowrap select-none",
            BADGE_TONE[phase],
          )}
        >
          <span
            aria-hidden
            className={cn("size-[7px] rounded-full", BADGE_DOT[phase])}
          />
          {BADGE_TEXT[phase]}
          <ChevronDown className="size-2.5 opacity-70 transition-transform group-data-[state=open]:rotate-180" />
        </PopoverTrigger>
        <PopoverContent
          align="end"
          sideOffset={8}
          className="w-[330px] rounded-[10px] p-0"
        >
          <div className="text-muted-foreground flex items-center justify-between border-b px-3.5 py-2.5 text-xs font-semibold">
            <span>RAG 知识库</span>
            <span>{CONN_LABEL[phase]}</span>
          </div>
          {RAGFLOW_DATASETS.map((name) => {
            const row = ragflowRow(
              phase,
              status.data?.datasets?.find((d) => d.name === name),
            );
            return (
              <div
                key={name}
                className="flex items-center gap-2.5 border-b px-3.5 py-2.5 text-[13px] last:border-b-0"
              >
                <span
                  aria-hidden
                  className={cn("size-[7px] shrink-0 rounded-full", row.dot)}
                />
                <span className="font-medium">{name}</span>
                <span className="text-muted-foreground ml-auto text-xs">
                  {row.meta}
                </span>
              </div>
            );
          })}
          <div className="text-muted-foreground bg-muted/50 px-3.5 py-2 text-[11.5px]">
            {footer}
          </div>
        </PopoverContent>
      </Popover>
      <Button
        size="sm"
        disabled={init.isPending || phase === "pending"}
        onClick={() => init.mutate()}
      >
        {init.isPending && <Loader2 className="size-3 animate-spin" />}
        {BUTTON_LABEL[phase]}
      </Button>
    </>
  );
}

export function SettingsView() {
  const { data, isLoading } = useConfig();
  const updateConfig = useUpdateConfig();
  const { data: ocrServiceNames } = useOcrServiceNames();
  const [form, setForm] = useState<CpaConfig | null>(null);
  const [dirty, setDirty] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    if (data && !form)
      setForm({ ...data, table_seeds: data.table_seeds ?? [] });
  }, [data, form]);

  if (isLoading || !form) {
    return (
      <div className="space-y-4 p-6">
        <PageHeader
          title="配置"
          description="表格定位规则与解析参数"
          icon={<PackageSearch />}
        />
        <Card>
          <CardContent className="p-6">
            <div className="bg-muted h-40 animate-pulse rounded" />
          </CardContent>
        </Card>
      </div>
    );
  }

  const set = <K extends keyof CpaConfig>(key: K, value: CpaConfig[K]) => {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setDirty(true);
  };

  const save = () => {
    if (!form) return;
    const clamped = {
      ...form,
      cluster_eps: clamp(Number(form.cluster_eps) || 0.6, 0.1, 1.0),
      cluster_min_samples: clamp(
        Math.round(Number(form.cluster_min_samples) || 2),
        1,
        10,
      ),
    };
    setForm(clamped); // 表单立即反映 clamp 后的值
    updateConfig.mutate(clamped, { onSuccess: () => setDirty(false) });
  };

  const discard = () => {
    if (!data) return;
    setForm({ ...data, table_seeds: data.table_seeds ?? [] });
    setDirty(false);
  };

  return (
    // EAI-CUSTOM: follow-up —— 与兄弟视图 space-y-6 p-8 统一(扩展级统一时处理)
    <div className="space-y-4 p-6">
      <PageHeader
        title="配置"
        description="表格定位规则与解析参数（修改后下次解析生效）"
        icon={<Settings />}
        actions={<RagflowHeaderActions />}
      />

      <SeedRulesCard
        seeds={form.table_seeds}
        onChange={(s) => set("table_seeds", s)}
        saving={updateConfig.isPending}
      />

      {/* OCR 提取引擎(cpa v3 M3 spec §3.3): 服务注册表在 /settings 基础配置维护。 */}
      <Card>
        <CardHeader>
          <CardTitle>OCR 提取引擎</CardTitle>
          <CardDescription>
            仅影响之后的解析与强制重 OCR，历史文档不受影响。服务在 系统设置 →
            基础配置 →「OCR 服务」注册。
          </CardDescription>
        </CardHeader>
        <CardContent className="max-w-md space-y-1.5">
          <Label htmlFor="ocr_provider">OCR 前端</Label>
          <Select
            value={form.ocr_provider ?? "builtin"}
            onValueChange={(v) =>
              set("ocr_provider", v === "builtin" ? null : v)
            }
          >
            <SelectTrigger id="ocr_provider" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="builtin">
                内建 eai-flow-ocr（RapidOCR）
              </SelectItem>
              {(ocrServiceNames ?? []).map((n) => (
                <SelectItem key={n} value={n}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {form.ocr_provider && form.ocr_provider !== "builtin" && (
            <p className="text-muted-foreground text-xs">
              已选外部服务「{form.ocr_provider}
              」。若该服务不可用，解析自动回退内建引擎并记录告警。
            </p>
          )}
        </CardContent>
      </Card>

      {/* 货物分组规则(2026-09-23): 聚类维度开关——名称恒开,规格/分类可切换,
          下次「聚类分析」生效。 */}
      <Card>
        <CardHeader>
          <CardTitle>货物分组规则</CardTitle>
          <CardDescription>
            选择聚类分组依据的维度（货物名称恒为依据）。修改后下次「聚类分析」生效。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-x-6 gap-y-2">
          <label className="text-foreground flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="accent-primary"
              checked
              disabled
            />
            货物名称（恒定依据）
          </label>
          <label className="text-foreground flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="accent-primary"
              checked={form.cluster_by_spec}
              onChange={(e) => set("cluster_by_spec", e.target.checked)}
            />
            按规格细分
          </label>
          <label className="text-foreground flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="accent-primary"
              checked={form.cluster_by_category}
              onChange={(e) => set("cluster_by_category", e.target.checked)}
            />
            按分类细分
          </label>
        </CardContent>
      </Card>

      <EvolutionCandidatesCard />

      <Card>
        <CardHeader>
          <CardTitle>定时任务</CardTitle>
          <CardDescription>启用后按 cron 表达式自动增量解析。</CardDescription>
        </CardHeader>
        <CardContent className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-foreground flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="accent-primary"
              checked={form.scheduled_enabled}
              onChange={(e) => set("scheduled_enabled", e.target.checked)}
            />
            启用定时解析
          </label>
          <div className="space-y-1.5">
            <label className="text-foreground text-sm font-medium">
              Cron 表达式
            </label>
            <Input
              value={form.schedule_cron ?? ""}
              placeholder="例如：0 2 * * *（每天 02:00）"
              onChange={(e) => set("schedule_cron", e.target.value || null)}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader
          className="cursor-pointer select-none"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          <CardTitle className="text-base">高级：聚类参数</CardTitle>
          <CardDescription>eps 越小归并越严格;一般无需调整。</CardDescription>
        </CardHeader>
        {showAdvanced && (
          <CardContent className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-foreground text-sm font-medium">
                聚类 eps（0.1–1.0）
              </label>
              <Input
                type="number"
                step="0.05"
                value={form.cluster_eps}
                onChange={(e) => set("cluster_eps", Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-foreground text-sm font-medium">
                最小成簇样本数（1–10）
              </label>
              <Input
                type="number"
                value={form.cluster_min_samples}
                onChange={(e) =>
                  set("cluster_min_samples", Number(e.target.value))
                }
              />
            </div>
          </CardContent>
        )}
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={updateConfig.isPending || !dirty}>
          <Save className="h-4 w-4" />
          {updateConfig.isPending ? "保存中…" : "保存配置"}
        </Button>
        {dirty && (
          <Button
            variant="ghost"
            disabled={updateConfig.isPending}
            onClick={discard}
          >
            放弃修改
          </Button>
        )}
        {dirty && (
          <span className="text-sm text-amber-600 dark:text-amber-400">
            有未保存修改
          </span>
        )}
        {updateConfig.isSuccess && !dirty && (
          <span className="text-success text-sm">已保存</span>
        )}
        {updateConfig.isError ? (
          <span className="text-destructive text-sm">
            保存失败：{updateConfig.error.message}
          </span>
        ) : null}
      </div>
    </div>
  );
}
