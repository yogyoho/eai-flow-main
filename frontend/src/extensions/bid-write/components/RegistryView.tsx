"use client";

import { BookMarked, Download, Info, Search, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/extensions/bid-write/api";
import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  MetricCell,
  MetricStrip,
  Overlay,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import { downloadCsv } from "@/extensions/bid-write/helpers";
import { useBidWriteRegistry } from "@/extensions/bid-write/hooks";
import type { RegistryAssertion } from "@/extensions/bid-write/types";

const SKILL_LABELS: Record<string, string> = {
  bid_letter: "投标函",
  price_sheet: "报价表",
  response_table: "响应/偏离表",
  attachment_index: "附件索引",
  cmn: "共享层",
};

const LEVEL_TONE = {
  D0: "bad",
  D1: "d1",
  D2: "d2",
  D3: "d3",
} as const;

export function RegistryView() {
  const query = useBidWriteRegistry();
  const [search, setSearch] = useState("");
  const [skill, setSkill] = useState("all");
  const [level, setLevel] = useState("all");
  const [selected, setSelected] = useState<RegistryAssertion | null>(null);

  const items = useMemo(() => query.data?.items ?? [], [query.data?.items]);
  const skills = useMemo(
    () => [...new Set(items.map((item) => item.skill))].sort(),
    [items],
  );
  const levels = useMemo(
    () => [...new Set(items.map((item) => item.level))].sort(),
    [items],
  );
  const rows = useMemo(
    () =>
      items.filter((item) => {
        if (skill !== "all" && item.skill !== skill) return false;
        if (level !== "all" && item.level !== level) return false;
        const term = search.trim().toLowerCase();
        if (!term) return true;
        return (
          item.id.toLowerCase().includes(term) ||
          item.name.toLowerCase().includes(term) ||
          item.expr.toLowerCase().includes(term) ||
          (item.rule_ref ?? "").toLowerCase().includes(term)
        );
      }),
    [items, level, search, skill],
  );

  const d0 = items.filter((item) => item.level === "D0").length;

  const exportRegistry = () => {
    if (items.length === 0) {
      toast.error("注册表尚未加载");
      return;
    }
    downloadCsv(
      "bid-write-断言注册表.csv",
      [
        "断言 ID",
        "名称",
        "技能",
        "等级",
        "阻断导出",
        "规则引用",
        "判定语义",
        "人工动作",
        "委托目标",
      ],
      items.map((item) => [
        item.id,
        item.name,
        item.skill,
        item.level,
        item.blocks_export ? "是" : "否",
        item.rule_ref ?? "",
        item.expr,
        item.human_action ?? "",
        item.delegates_to ?? "",
      ]),
    );
    toast.success(`已导出 ${items.length} 条断言`);
  };

  return (
    <>
      <PageHead
        icon={BookMarked}
        title="断言注册表"
        subtitle="P0 四技能 + CMN 共享层 · 只读真源（后端 assertions/p0.yaml）"
        actions={
          <button
            type="button"
            className="btn btn-sm"
            onClick={exportRegistry}
            disabled={items.length === 0}
          >
            <Download size={13} aria-hidden="true" />
            导出 CSV
          </button>
        }
      />

      {query.isLoading ? (
        <LoadingBlock label="正在加载断言注册表…" />
      ) : query.error instanceof ApiError && query.error.status === 404 ? (
        <EmptyState
          icon={BookMarked}
          title="断言注册表接口尚未启用"
          description="当前 Gateway 未提供 /api/extensions/bid-write/registry（HTTP 404）。请确认 bid-write 扩展已加载并重启 Gateway 后重试。"
          action={
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void query.refetch()}
            >
              重新检查
            </button>
          }
        />
      ) : query.error ? (
        <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <>
          <MetricStrip>
            <MetricCell
              label="断言总数"
              value={items.length}
              suffix="条"
              accent
            />
            <MetricCell label="D0 阻断级" value={d0} tone="err" />
            <MetricCell label="技能域" value={skills.length} />
            <MetricCell
              label="schema"
              value={query.data?.schema_version ?? "—"}
            />
          </MetricStrip>

          <div className="card">
            <div className="card-h">
              <h3>等级行为表</h3>
              <span className="r">
                <Badge tone="gray">加载期静态校验 · 只读</Badge>
              </span>
            </div>
            <div className="card-b">
              <div className="lv-grid">
                {Object.entries(query.data?.levels ?? {}).map(
                  ([code, entry]) => (
                    <div className="lv" key={code}>
                      <div className="lv-h">
                        <Badge
                          tone={
                            LEVEL_TONE[code as keyof typeof LEVEL_TONE] ??
                            "gray"
                          }
                        >
                          {code}
                        </Badge>
                        <b>{entry.name ?? code}</b>
                      </div>
                      <div className="lv-body">
                        <span>导出门禁</span>
                        <b>{entry.blk ? "阻断" : "不阻断"}</b>
                        <span>渲染</span>
                        <b>{entry.render ?? "—"}</b>
                        <span>预审状态</span>
                        <b>{entry.pre_review_state ?? "—"}</b>
                        <span>重试</span>
                        <b>{entry.retry ?? "—"}</b>
                      </div>
                    </div>
                  ),
                )}
              </div>
            </div>
          </div>

          <div className="card bw-mt">
            <div className="card-h">
              <h3>断言明细</h3>
              <span className="r">
                <span className="bw-search">
                  <Search size={13} aria-hidden="true" />
                  <input
                    className="inp"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="搜索 ID / 名称 / 规则"
                    aria-label="搜索断言"
                  />
                </span>
                <select
                  className="select bw-select"
                  value={skill}
                  onChange={(event) => setSkill(event.target.value)}
                  aria-label="按技能筛选"
                >
                  <option value="all">全部技能</option>
                  {skills.map((item) => (
                    <option key={item} value={item}>
                      {SKILL_LABELS[item] ?? item}
                    </option>
                  ))}
                </select>
                <select
                  className="select bw-select"
                  value={level}
                  onChange={(event) => setLevel(event.target.value)}
                  aria-label="按等级筛选"
                >
                  <option value="all">全部等级</option>
                  {levels.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </span>
            </div>
            {rows.length === 0 ? (
              <div className="card-b">
                <EmptyState
                  icon={BookMarked}
                  title="没有匹配的断言"
                  description="调整搜索词、技能或等级筛选。"
                />
              </div>
            ) : (
              <div className="tbl-wrap">
                <table className="tbl bw-registry-table">
                  <thead>
                    <tr>
                      <th>断言 ID</th>
                      <th>名称</th>
                      <th>技能</th>
                      <th>等级</th>
                      <th>导出门禁</th>
                      <th>规则引用</th>
                      <th>人工动作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((item) => (
                      <tr
                        key={item.id}
                        onClick={() => setSelected(item)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            setSelected(item);
                          }
                        }}
                        tabIndex={0}
                      >
                        <td className="mono bw-nowrap">{item.id}</td>
                        <td>{item.name}</td>
                        <td>{SKILL_LABELS[item.skill] ?? item.skill}</td>
                        <td>
                          <Badge
                            tone={
                              LEVEL_TONE[
                                item.level as keyof typeof LEVEL_TONE
                              ] ?? "gray"
                            }
                          >
                            {item.level}
                          </Badge>
                        </td>
                        <td>
                          {item.blocks_export ? (
                            <Badge tone="bad" dot>
                              阻断
                            </Badge>
                          ) : (
                            <Badge tone="gray">不阻断</Badge>
                          )}
                        </td>
                        <td className="mono">{item.rule_ref ?? "—"}</td>
                        <td>
                          <span
                            className="excerpt ellipsis"
                            title={item.human_action ?? ""}
                          >
                            {item.human_action ?? "自动闭环"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="card-b">
              <div className="banner info">
                <Info size={15} aria-hidden="true" />
                <span>
                  注册表为静态内容（禁热改）。D0 必须阻断导出；rule_ref 悬空由
                  CI 期测试拦截。点击任意行查看判定语义与委托链。
                </span>
              </div>
            </div>
          </div>
        </>
      )}

      <Overlay
        open={selected !== null}
        title={selected?.id ?? "断言详情"}
        subtitle={
          selected
            ? (SKILL_LABELS[selected.skill] ?? selected.skill)
            : undefined
        }
        onClose={() => setSelected(null)}
        footer={
          <button
            type="button"
            className="btn pri"
            onClick={() => setSelected(null)}
          >
            关闭
          </button>
        }
      >
        {selected ? (
          <>
            <div className="kv-list">
              <span className="k">名称</span>
              <span className="v">{selected.name}</span>
              <span className="k">等级</span>
              <span className="v">
                <Badge
                  tone={
                    LEVEL_TONE[selected.level as keyof typeof LEVEL_TONE] ??
                    "gray"
                  }
                >
                  {selected.level}
                </Badge>
              </span>
              <span className="k">导出门禁</span>
              <span className="v">
                {selected.blocks_export ? (
                  <Badge tone="bad" dot>
                    阻断导出
                  </Badge>
                ) : (
                  "不阻断"
                )}
              </span>
              <span className="k">规则引用</span>
              <span className="v mono">{selected.rule_ref ?? "—"}</span>
              <span className="k">委托目标</span>
              <span className="v mono">{selected.delegates_to ?? "—"}</span>
              <span className="k">人工动作</span>
              <span className="v">{selected.human_action ?? "自动闭环"}</span>
            </div>
            <div className="bw-requirement bw-mt">
              <span className="k">判定语义</span>
              <p className="mono bw-pre-wrap">{selected.expr}</p>
            </div>
            <div className="bw-check-line bw-mt">
              <ShieldCheck size={14} aria-hidden="true" />
              只读注册表，不允许在运行时编辑
            </div>
          </>
        ) : null}
      </Overlay>
    </>
  );
}
