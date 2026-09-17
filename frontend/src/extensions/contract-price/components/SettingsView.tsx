"use client";

/** 配置页 v3: seed 规则库(主) + 定时任务 + 聚类高级参数(折叠)。
 *  移除: 解析模式(v2 已废弃单一 OCR 路径)与货物表名关键字(被 seed 库取代)。
 *  dirty 跟踪 + 保存 clamp + toast 自动消隐。 */

import { PackageSearch, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import { SeedRulesCard } from "@/extensions/contract-price/components/SeedRulesCard";
import { useConfig, useUpdateConfig } from "@/extensions/contract-price/hooks";
import type { CpaConfig } from "@/extensions/contract-price/types";

const clamp = (v: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, v));

export function SettingsView() {
  const { data, isLoading } = useConfig();
  const updateConfig = useUpdateConfig();
  const [form, setForm] = useState<CpaConfig | null>(null);
  const [dirty, setDirty] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    if (data && !form)
      setForm({ ...data, table_seeds: data.table_seeds ?? [] });
  }, [data, form]);

  if (isLoading || !form) {
    return (
      <div className="p-8">
        <PageHeader
          title="配置"
          description="表格定位规则与解析参数"
          icon={<PackageSearch className="h-4 w-4" />}
        />
        <Card className="mt-6">
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
    updateConfig.mutate(
      {
        ...form,
        cluster_eps: clamp(Number(form.cluster_eps) || 0.6, 0.1, 1.0),
        cluster_min_samples: clamp(
          Math.round(Number(form.cluster_min_samples) || 2),
          1,
          10,
        ),
      },
      { onSuccess: () => setDirty(false) },
    );
  };

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="配置"
        description="表格定位规则与解析参数（修改后下次解析生效）"
        icon={<PackageSearch className="h-4 w-4" />}
      />

      <SeedRulesCard
        seeds={form.table_seeds}
        onChange={(s) => set("table_seeds", s)}
        saving={updateConfig.isPending}
      />

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
        {dirty && <span className="text-sm text-amber-600">有未保存修改</span>}
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
