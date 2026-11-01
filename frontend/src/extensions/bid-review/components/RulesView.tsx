"use client";

/**
 * EAI-CUSTOM (2026-10-30): 规则库页按 2026-10-30 原型重整(参照 docs/designs/2026-10-30-bid-review-ui.html
 * #s9;类词汇 = app/bid-review/bid-review.css 的 .brx 作用域,弃 2026-10-29 spec 的
 * FilterPills/GroupCard 组合)。结构 = page-head(标题+hd-sub+刷新)→ 规则包头卡(name/
 * version/stage-chip rule_count/enabled pill + 只读 Switch)→ 层级过滤 .seg(M5 §4.7:
 * 全部/L1 实质性/L3 一致性/高误报,替换旧类型词汇)→ 高误报段互跳 note-bar → 全量规则表
 * .tbl(共享 RuleStatsTable,M5 加判定算子列;点规则 id 开五块定义抽屉)→ tbl-foot
 * 误报率口径 → note-bar 启停说明。
 * M5(§4.7):B5 规则定义抽屉(GET /rulepacks/{name}/rules 五块,只读,修订须走规则包
 * 版本发布);s9↔s10 互跳——高误报段 → /metrics#fail-list;FAIL 行深链 ?rule= 直开抽屉。
 * 数据契约不变 = GET /rulepacks(RulePackOut + stats 人工复核回流);规则启停无写端点,
 * Switch 恒 disabled——启停走规则包版本发布,前端不提供开关。
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Switch } from "@/components/ui/switch";
import { type RuleExprOut } from "@/extensions/bid-review/api";
import {
  type RuleStatsRow,
  RuleStatsTable,
  isHighFp,
} from "@/extensions/bid-review/components/rulepack-ui";
import {
  useBidRuleExprs,
  useBidRulepacks,
} from "@/extensions/bid-review/hooks";

/** 层级过滤档(M5 §4.7,.seg):全部 + L1 实质性 + L3 一致性 + 高误报(误报率≥20% 且有命中)。 */
const LAYER_FILTERS = ["all", "L1", "L3", "highfp"] as const;

type LayerFilter = (typeof LAYER_FILTERS)[number];

const LAYER_LABELS: Record<LayerFilter, string> = {
  all: "全部",
  L1: "L1 实质性",
  L3: "L3 一致性",
  highfp: "高误报",
};

export function RulesView() {
  const rulepacksQuery = useBidRulepacks();
  // 层级 seg(M5):高误报段 = isHighFp(stats);deep link ?rule= 直开抽屉(s10 FAIL 行互跳②)
  const searchParams = useSearchParams();
  const [layer, setLayer] = useState<LayerFilter>("all");
  const [drawerRule, setDrawerRule] = useState<string | null>(() =>
    searchParams.get("rule"),
  );
  const exprQuery = useBidRuleExprs(
    drawerRule ? (rulepacksQuery.data?.[0]?.name ?? null) : null,
  );

  // 生产单规则包(api 返回数组,沿用 data[0] 取包;多包聚合属效果看板职责)
  const pack = rulepacksQuery.data?.[0] ?? null;
  const packRules = pack?.rules ?? [];
  const matches = (r: (typeof packRules)[number]) =>
    layer === "all"
      ? true
      : layer === "highfp"
        ? isHighFp(pack?.stats[r.id] ?? {})
        : r.layer === layer;
  const rules = packRules.filter(matches);
  const packEnabled = pack?.enabled ?? false;

  const filterOptions = LAYER_FILTERS.map((value) => ({
    value,
    label: LAYER_LABELS[value],
    count: packRules.filter((r) =>
      value === "all"
        ? true
        : value === "highfp"
          ? isHighFp(pack?.stats[r.id] ?? {})
          : r.layer === value,
    ).length,
  }));

  const rows: RuleStatsRow[] = rules.map((rule) => ({
    key: rule.id,
    rule,
    op: rule.op ?? null,
    stat: pack?.stats[rule.id] ?? {},
  }));

  return (
    <div className="screen on">
      <div className="page-head">
        <div>
          <h2>规则库</h2>
          <p className="hd-sub">
            {pack
              ? "查看规则定义与人工复核回流统计（误报/采纳）——本页只读，修订走规则包新版本发布"
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
                aria-label="层级筛选"
              >
                {filterOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={layer === opt.value}
                    className={layer === opt.value ? "on" : undefined}
                    onClick={() => setLayer(opt.value)}
                  >
                    {opt.label} {opt.count}
                  </button>
                ))}
              </div>

              {/* 互跳①(M5 §4.7):高误报段 → 看板 FAIL 名单锚点 */}
              {layer === "highfp" ? (
                <div className="note-bar warnbar" style={{ marginBottom: 12 }}>
                  <span style={{ flex: 1 }}>
                    高误报段：误报率 ≥ 20% 且有命中的规则——先到看板确认 FAIL
                    归因，再决定是否修订。
                  </span>
                  <Link
                    href="/bid-review/metrics#fail-list"
                    className="btn btn-sec btn-sm"
                  >
                    查看 FAIL 名单
                  </Link>
                </div>
              ) : null}

              <div className="card">
                {rules.length === 0 ? (
                  <div className="tbl-foot">该层级暂无规则</div>
                ) : (
                  <RuleStatsTable rows={rows} onRuleClick={setDrawerRule} />
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

      {drawerRule ? (
        <RuleDrawer
          ruleId={drawerRule}
          query={exprQuery}
          onClose={() => setDrawerRule(null)}
        />
      ) : null}
    </div>
  );
}

/** 规则定义抽屉(B5,M5 §4.7,原型 ruleDrawer):五块 expr-block 只读 + 版本发布 foot。 */
function RuleDrawer({
  ruleId,
  query,
  onClose,
}: {
  ruleId: string;
  query: { data?: RuleExprOut[]; isPending: boolean };
  onClose: () => void;
}) {
  const d = (query.data ?? []).find((x) => x.id === ruleId);
  return (
    <div
      className="drawer-wrap open"
      role="dialog"
      aria-label={`规则定义 ${ruleId}`}
    >
      <div className="drawer-scrim" onClick={onClose} />
      <div className="drawer" style={{ maxWidth: 560 }}>
        <div className="drawer-hd">
          <h3>规则定义 · {ruleId}</h3>
          <button
            type="button"
            className="x"
            aria-label="关闭"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        {!d ? (
          <div className="note-bar">
            <span>
              {query.isPending
                ? "规则定义加载中…"
                : "未找到该规则定义（规则包可能已更新）"}
            </span>
          </div>
        ) : (
          <>
            <div className="expr-block">
              <div className="expr-hd">PRECONDITION</div>
              <pre>{d.precondition ?? "(无前置条件)"}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">EXPR{d.op ? ` · ${d.op}` : ""}</div>
              <pre>{d.expr_lines.join("\n")}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">ON_MISSING_INPUT</div>
              <pre>{d.on_missing_input ?? "(未约定)"}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">MESSAGE_TPL</div>
              <pre>{d.message_tpl}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">FIX_TPL</div>
              <pre>{d.fix_tpl || "(无)"}</pre>
            </div>
            <div className="tbl-foot">
              本页只读 · 修订须走规则包版本发布（新版本号 + 评测对照）
            </div>
          </>
        )}
      </div>
    </div>
  );
}
