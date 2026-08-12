"use client";

import { PackageSearch, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader } from "@/extensions/spare-parts/components/PageHeader";
import { useConfig, useUpdateConfig } from "@/extensions/spare-parts/hooks";
import type { CspConfig } from "@/extensions/spare-parts/types";

export function SettingsView() {
  const { data, isLoading } = useConfig();
  const updateConfig = useUpdateConfig();
  const [form, setForm] = useState<CspConfig | null>(null);

  useEffect(() => {
    if (data) {
      setForm({
        parse_mode: data.parse_mode,
        cluster_eps: data.cluster_eps,
        cluster_min_samples: data.cluster_min_samples,
        scheduled_enabled: data.scheduled_enabled,
        schedule_cron: data.schedule_cron,
        price_table_keywords: data.price_table_keywords ?? [],
      });
    }
  }, [data]);

  if (isLoading || !form) {
    return (
      <div className="p-8">
        <PageHeader title="配置" description="分组参数与定时任务设置" icon={<PackageSearch className="w-4 h-4" />} />
        <Card className="mt-6">
          <CardContent className="p-6">
            <div className="h-40 animate-pulse rounded bg-muted" />
          </CardContent>
        </Card>
      </div>
    );
  }

  const set = <K extends keyof CspConfig>(key: K, value: CspConfig[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  return (
    <div className="space-y-6 p-8">
      <PageHeader title="配置" description="聚类参数与定时任务设置（修改后下次分析生效）" />

      <Card>
        <CardHeader>
          <CardTitle>解析与聚类</CardTitle>
          <CardDescription>
            解析模式决定合同分项的提取方式；聚类 eps 越小，归并越严格。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">解析模式</label>
            <Select value={form.parse_mode} onValueChange={(v) => set("parse_mode", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="table">表格</SelectItem>
                <SelectItem value="list">清单列表</SelectItem>
                <SelectItem value="mixed">混合（表格优先）</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">聚类 eps（相似度距离阈值）</label>
            <Input
              type="number"
              step="0.05"
              min="0.1"
              max="1.0"
              value={form.cluster_eps}
              onChange={(e) => set("cluster_eps", Number(e.target.value))}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">最小成簇样本数</label>
            <Input
              type="number"
              min="1"
              max="10"
              value={form.cluster_min_samples}
              onChange={(e) => set("cluster_min_samples", Number(e.target.value))}
            />
          </div>

          <div className="space-y-1.5 sm:col-span-2">
            <label className="text-sm font-medium text-foreground">货物表名关键字</label>
            <textarea
              className="flex min-h-[88px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.price_table_keywords.join("\n")}
              placeholder={"每行一个，如：\n工程量清单\n设备清单\n报价单"}
              onChange={(e) =>
                set(
                  "price_table_keywords",
                  e.target.value
                    .split(/[\n,，]/)
                    .map((s) => s.trim())
                    .filter(Boolean)
                )
              }
            />
            <p className="text-xs text-muted-foreground">
              表首含任一关键字的表强判定为货物表（即使列头无明确单价）。不同合同表名不同，按项目定制。下次分析生效。
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>定时任务</CardTitle>
          <CardDescription>启用后按 cron 表达式自动增量分析。</CardDescription>
        </CardHeader>
        <CardContent className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={form.scheduled_enabled}
              onChange={(e) => set("scheduled_enabled", e.target.checked)}
              className="accent-primary"
            />
            启用定时分析
          </label>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">Cron 表达式</label>
            <Input
              value={form.schedule_cron ?? ""}
              placeholder="例如：0 2 * * *（每天 02:00）"
              onChange={(e) => set("schedule_cron", e.target.value || null)}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={() => updateConfig.mutate(form)} disabled={updateConfig.isPending}>
          <Save className="h-4 w-4" />
          {updateConfig.isPending ? "保存中…" : "保存配置"}
        </Button>
        {updateConfig.isSuccess ? (
          <span className="text-sm text-success">已保存</span>
        ) : null}
        {updateConfig.isError ? (
          <span className="text-sm text-destructive">
            保存失败：{(updateConfig.error).message}
          </span>
        ) : null}
      </div>
    </div>
  );
}
