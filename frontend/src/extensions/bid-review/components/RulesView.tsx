"use client";

/**
 * EAI-CUSTOM (2026-10-30): 规则库页按 2026-10-30 原型重整(参照 docs/designs/2026-10-30-bid-review-ui.html
 * #s9;类词汇 = app/bid-review/bid-review.css 的 .brx 作用域,弃 2026-10-29 spec 的
 * FilterPills/GroupCard 组合)。结构 = page-head(标题+hd-sub+刷新)→ 规则包头卡(name/
 * version/stage-chip rule_count/enabled pill + 只读 Switch)→ 类型过滤 .seg(替换
 * FilterPills)→ 全量规则表 .tbl(共享 RuleStatsTable,列契约见 rulepack-ui.tsx)→
 * tbl-foot 误报率口径 → note-bar 启停说明。
 * 数据契约不变 = GET /rulepacks(RulePackOut + stats 人工复核回流);规则启停无写端点,
 * Switch 恒 disabled——启停走规则包版本发布,前端不提供开关。
 */

import { useState } from "react";

import { Switch } from "@/components/ui/switch";
import {
  type RuleStatsRow,
  RuleStatsTable,
} from "@/extensions/bid-review/components/rulepack-ui";
import { useBidRulepacks } from "@/extensions/bid-review/hooks";

/** 类型过滤档(.seg):全部 + det/sem/hyb;值 = 规则包 YAML 的 type 词汇。 */
const TYPE_FILTERS = ["all", "deterministic", "semantic", "hybrid"] as const;

type TypeFilter = (typeof TYPE_FILTERS)[number];

const FILTER_LABELS: Record<TypeFilter, string> = {
  all: "全部",
  deterministic: "det",
  semantic: "sem",
  hybrid: "hyb",
};

export function RulesView() {
  const rulepacksQuery = useBidRulepacks();
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");

  // 生产单规则包(api 返回数组,沿用 data[0] 取包;多包聚合属效果看板职责)
  const pack = rulepacksQuery.data?.[0] ?? null;
  const packRules = pack?.rules ?? [];
  const rules = packRules.filter(
    (r) => typeFilter === "all" || r.type === typeFilter,
  );
  const packEnabled = pack?.enabled ?? false;

  const filterOptions = TYPE_FILTERS.map((value) => ({
    value,
    label: FILTER_LABELS[value],
    count:
      value === "all"
        ? packRules.length
        : packRules.filter((r) => r.type === value).length,
  }));

  const rows: RuleStatsRow[] = rules.map((rule) => ({
    key: rule.id,
    rule,
    stat: pack?.stats[rule.id] ?? {},
  }));

  return (
    <div className="screen on">
      <div className="page-head">
        <div>
          <h2>规则库</h2>
          <p className="hd-sub">
            {pack
              ? `规则包 ${pack.name} v${pack.version} · 共 ${pack.rule_count} 条 · 统计来自人工复核回流（误报/采纳）`
              : "生产规则包清单与人工复核回流统计"}
          </p>
        </div>
        <div className="ph-actions">
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void rulepacksQuery.refetch()}
            disabled={rulepacksQuery.isFetching}
          >
            刷新
          </button>
        </div>
      </div>

      {rulepacksQuery.isError ? (
        <div className="note-bar errbar" role="alert">
          <span>规则包加载失败：{rulepacksQuery.error.message}</span>
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void rulepacksQuery.refetch()}
          >
            重试
          </button>
        </div>
      ) : null}

      {rulepacksQuery.isPending ? (
        <div className="card">
          <div className="tbl-foot">规则包加载中…</div>
        </div>
      ) : pack ? (
        <>
          {/* 规则包头卡：name / version / stage-chip rule_count / enabled pill + 只读 Switch */}
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="card-hd">
              <h3>{pack.name}</h3>
              <span className="hd-sub">v{pack.version}</span>
              <span className="stage-chip">
                规则 <span className="cnt">{pack.rule_count}</span>
              </span>
              <span className={packEnabled ? "pill pill-ok" : "pill pill-gray"}>
                {packEnabled ? "已启用" : "已停用"}
              </span>
              <div className="hd-right">
                <span className="hd-sub">启用</span>
                {/* 后端无规则启停写端点：Switch 只读展示，启停走规则包版本发布 */}
                <Switch
                  checked={packEnabled}
                  disabled
                  aria-label="规则包启用（只读）"
                />
              </div>
            </div>
          </div>

          {packRules.length === 0 ? (
            <div className="card">
              <div className="tbl-foot">规则包暂无规则</div>
            </div>
          ) : (
            <>
              <div
                className="seg"
                style={{ marginBottom: 12 }}
                role="group"
                aria-label="规则类型过滤"
              >
                {filterOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={typeFilter === opt.value}
                    className={typeFilter === opt.value ? "on" : undefined}
                    onClick={() => setTypeFilter(opt.value)}
                  >
                    {opt.label} {opt.count}
                  </button>
                ))}
              </div>

              <div className="card">
                {rules.length === 0 ? (
                  <div className="tbl-foot">该类型暂无规则</div>
                ) : (
                  <RuleStatsTable rows={rows} />
                )}
                <div className="tbl-foot">
                  误报率 = 复核判误报次数 /
                  该规则命中次数；≥20%（高误报）自动回流评测集并进入规则效果看板
                  FAIL 名单
                </div>
              </div>
            </>
          )}

          <div className="note-bar">
            规则启停走规则包版本发布，前端不提供开关。
          </div>
        </>
      ) : (
        <div className="card">
          <div className="tbl-foot">暂无规则包</div>
        </div>
      )}
    </div>
  );
}
