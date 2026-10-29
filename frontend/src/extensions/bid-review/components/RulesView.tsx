"use client";

/**
 * 规则库页(bid:page:rules)——Task 17 Step 3。
 * 视觉规范:docs/designs/2026-10-29-bid-review-ui-spec.md §3.4(FilterPills 类型过滤 +
 * L1/L3 分组网格 + GroupCard 卡:类型/severity Pill + 开关 + 命中/误报/采纳统计行)。
 * 数据 = GET /rulepacks(生产规则包 + DB stats 回流);开关为服务级 enabled 只读展示
 * (后端无规则启停写端点,Switch disabled,关闭时整卡 muted)。
 */

import { ScrollText } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  GroupCard,
  severityPill,
} from "@/extensions/bid-review/components/primitives";
import { useBidRulepacks } from "@/extensions/bid-review/hooks";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import { Pill } from "@/extensions/contract-price/components/ui/bits";
import { FilterPills } from "@/extensions/project/components/FilterPills";

/** 类型 Pill 标签(spec §3.4:det/sem/hyb);值=规则包 YAML 的 type 词汇。 */
const TYPE_LABELS: Record<string, string> = {
  deterministic: "det",
  semantic: "sem",
  hybrid: "hyb",
};

const FILTERS = [
  { value: "all", label: "全部" },
  { value: "deterministic", label: "det" },
  { value: "semantic", label: "sem" },
  { value: "hybrid", label: "hyb" },
];

export function RulesView() {
  const rulepacksQuery = useBidRulepacks();
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const pack = rulepacksQuery.data?.[0] ?? null;
  const rules = (pack?.rules ?? []).filter(
    (r) => typeFilter === "all" || r.type === typeFilter,
  );
  const layers = ["L1", "L3"];
  const packEnabled = pack?.enabled ?? false;

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-4 p-6">
      <div className="shrink-0">
        <PageHeader
          title="规则库"
          description={
            pack
              ? `${pack.name} v${pack.version} · ${pack.rule_count} 条规则 · 统计由人工复核回流(false_positive→误报,confirm→采纳)`
              : "生产规则包清单与人工复核统计"
          }
          icon={<ScrollText />}
          actions={
            <Button
              variant="outline"
              size="sm"
              onClick={() => void rulepacksQuery.refetch()}
              disabled={rulepacksQuery.isFetching}
            >
              刷新
            </Button>
          }
        />
      </div>

      {/* 类型过滤 FilterPills(§3.4;共享组件 ui-style-spec §7 语义) */}
      <div className="flex items-center gap-2">
        <FilterPills
          pills={FILTERS}
          value={typeFilter}
          onChange={setTypeFilter}
        />
        <span className="text-muted-foreground text-xs tabular-nums">
          {rules.length} 条
        </span>
      </div>

      {rulepacksQuery.isError ? (
        <div className="bg-destructive/10 text-destructive flex items-center gap-2 rounded-md px-3 py-2 text-xs">
          <span className="flex-1">
            规则包加载失败:{rulepacksQuery.error.message}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void rulepacksQuery.refetch()}
          >
            重试
          </Button>
        </div>
      ) : null}

      {rulepacksQuery.isPending ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="border-border bg-card h-28 animate-pulse rounded-lg border"
            />
          ))}
        </div>
      ) : !pack || rules.length === 0 ? (
        <div className="border-border flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16">
          <p className="text-muted-foreground text-sm">暂无规则</p>
        </div>
      ) : (
        layers
          .map((layer) => ({
            layer,
            items: rules.filter((r) => r.layer === layer),
          }))
          .filter((g) => g.items.length > 0)
          .map((group) => (
            <section key={group.layer} className="flex flex-col gap-3">
              {/* 组标题 text-base font-semibold + 计数(§3.4) */}
              <div className="flex items-baseline gap-2">
                <h2 className="text-foreground text-base font-semibold">
                  {group.layer}
                </h2>
                <span className="text-muted-foreground text-xs tabular-nums">
                  {group.items.length} 条
                </span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {group.items.map((rule) => {
                  const sp = severityPill(rule.severity);
                  const stats = pack.stats[rule.id] ?? {};
                  return (
                    <GroupCard
                      key={rule.id}
                      title={rule.name}
                      subtitle={rule.id}
                      className={packEnabled ? undefined : "opacity-60"}
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Pill tone="gray" title={`类型 ${rule.type}`}>
                          {TYPE_LABELS[rule.type] ?? rule.type}
                        </Pill>
                        <Pill tone={sp.tone}>{sp.label}</Pill>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground text-xs">
                          启用
                        </span>
                        {/* 开关:后端无规则启停写端点,服务级 enabled 只读展示(§3.4 disabled 卡整体 muted) */}
                        <Switch checked={packEnabled} disabled />
                      </div>
                      {/* 统计行:命中/误报/采纳(§3.4 text-xs tabular-nums) */}
                      <div className="text-muted-foreground text-xs tabular-nums">
                        命中 {stats.hit ?? 0} · 误报 {stats.fp ?? 0} · 采纳{" "}
                        {stats.adopted ?? 0}
                      </div>
                    </GroupCard>
                  );
                })}
              </div>
            </section>
          ))
      )}
    </div>
  );
}
