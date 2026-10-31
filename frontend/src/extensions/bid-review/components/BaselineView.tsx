"use client";

/**
 * 基准确认页(bid:page:baseline)。
 * EAI-CUSTOM (2026-10-30): 参照 docs/designs/2026-10-30-bid-review-ui.html 原型
 * s4(基准确认卡点),字段对照在此分区呈现:
 * - 字段对照(s3/s4 一期):GET /tasks/{id}/baselines 行级快照 → 按首段路径族
 *   (tender/bid)分组,字段卡核对(值/出处/「查看原文」定位弹层)。
 *   Plan6 (2026-10-31,spec §4.3):解析质量表已迁 /parsing 归拢专屏。
 * EAI-CUSTOM (2026-10-31 二期 spec §1.5/§二/§四):冲突裁定卡(多候选 radio +
 * 采纳 → adjudicate 端点;已裁定转pill)、置信 pill(高/低/未核验,quote 服务端
 * 核验为真信号)、字段中文名(labels 投影,path 降为 mono 小字)、确认门计数
 * 加未裁定冲突数。
 * 类词汇表=app/bid-review/bid-review.css(.brx 词汇:tbl/split/fam- 系列/f-card/gate-bar)。
 * 行为契约不变:useBidTask 详情 + useBidConfirmTask 确认门;仅 awaiting_confirm 可确认
 * (gateOpen gating);409 分流 toast 展示后端 detail(未复核致命/未裁定冲突)。
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  type BidBaselineRow,
  type LocateTarget,
} from "@/extensions/bid-review/api";
// 共享词汇(Plan6 自本文件上移,ParsingView 同用;裁定交互仍留本文件)
import {
  FAMILIES,
  familyOf,
  NO_LABELS,
  STATUS_PILL_CLASS,
  confPill,
  fieldRows,
  formatVal,
} from "@/extensions/bid-review/components/baselineFields";
import { DocLocateModal } from "@/extensions/bid-review/components/DocLocateModal";
import { taskStatusPill } from "@/extensions/bid-review/components/primitives";
import { TaskTitleTag } from "@/extensions/bid-review/components/TaskTitleTag";
import {
  useBidAdjudicate,
  useBidBaselines,
  useBidConfirmTask,
  useBidTask,
} from "@/extensions/bid-review/hooks";

export function BaselineView({ taskId }: { taskId?: string | null }) {
  const taskQuery = useBidTask(taskId ?? null);
  const baselinesQuery = useBidBaselines(taskId ?? null);
  const confirm = useBidConfirmTask();

  const task = taskQuery.data ?? null;
  const gateOpen = task?.status === "awaiting_confirm";
  const data = baselinesQuery.data;
  const rows = useMemo(() => data?.items ?? [], [data]);
  const labels = data?.labels ?? NO_LABELS;
  const adjudications = data?.adjudications ?? {};
  const [fam, setFam] = useState<string>("tender");
  const [search, setSearch] = useState("");
  const [locate, setLocate] = useState<LocateTarget | null>(null);
  const [picks, setPicks] = useState<Record<string, number>>({});
  const adjudicate = useBidAdjudicate(taskId ?? "");

  // 冲突路径(全行并集;候选清单各行同源,取首行);已裁定路径不计未裁
  const conflictPaths = useMemo(() => {
    const all = new Set<string>();
    for (const r of rows) for (const p of r.conflicts ?? []) all.add(p);
    return [...all].sort();
  }, [rows]);
  const unresolvedCount = conflictPaths.filter(
    (p) => adjudications[p] === undefined,
  ).length;
  const conflictCands = rows[0]?.candidates ?? {};

  // 字段族计数(全快照口径,不随筛选变);检索只过滤当前族展示
  const allRows = useMemo(() => fieldRows(rows[0], labels), [rows, labels]);
  const famStats = useMemo(() => {
    const m = new Map<string, { total: number; missing: number }>();
    for (const f of allRows) {
      const k = familyOf(f.path);
      const cur = m.get(k) ?? { total: 0, missing: 0 };
      cur.total += 1;
      if (f.missing) cur.missing += 1;
      m.set(k, cur);
    }
    return m;
  }, [allRows]);
  const famKey = famStats.has(fam) ? fam : (FAMILIES[0]?.key ?? "");
  const shown = allRows.filter(
    (f) =>
      familyOf(f.path) === famKey &&
      (search === "" || f.path.toLowerCase().includes(search.toLowerCase())),
  );
  const missingTotal = allRows.filter((f) => f.missing).length;

  useEffect(() => {
    if (confirm.isError) {
      // 二期:后端 confirm 门 409 detail 已分流(未复核致命项 / 未裁定冲突 N 个),透传
      toast.error(confirm.error?.message ?? "确认失败");
    }
  }, [confirm.isError, confirm.error]);

  if (!taskId) {
    return (
      <div className="screen on">
        <div className="page-head">
          <div className="ph-icon">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden>
              <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
            </svg>
          </div>
          <div>
            <h2>基准确认</h2>
            <div className="ph-sub">
              逐条核对基准后再确认——基准错误将批量产生错误结论
            </div>
          </div>
        </div>
        <div className="note-bar warnbar">
          <svg className="ic" viewBox="0 0 24 24" aria-hidden>
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <path d="M12 9v4M12 17h.01" />
          </svg>
          <span>未指定任务——请从任务列表进入。</span>
        </div>
        <Link
          href="/bid-review"
          className="btn btn-sec"
          style={{ marginTop: 12 }}
        >
          返回任务列表
        </Link>
      </div>
    );
  }

  const st = task ? taskStatusPill(task.status) : null;
  const unconfirmedRows = rows.filter((r) => !r.confirmed).length;
  // 门进度:仅 awaiting_confirm 且(行全确认 + 冲突全裁定)才 100%
  const gatePct =
    gateOpen && unconfirmedRows + unresolvedCount > 0 ? 0 : task ? 100 : 0;

  return (
    <div className="screen on">
      <div className="proto-banner">
        <b>P0-2b/P0-3</b>· 解析与字段抽取 + 基准确认卡点 · 人工核对基准包 →
        解锁审查 · 未确认不得进入审查(不可绕过)
      </div>

      <div className="page-head">
        <div className="ph-icon">
          <svg className="ic" viewBox="0 0 24 24" aria-hidden>
            <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
          </svg>
        </div>
        <div>
          <h2>
            招标基准确认
            <TaskTitleTag taskId={taskId} bizNo={task?.biz_no} />
          </h2>
          <div className="ph-sub">
            确认招标要求——未完成将不能开始审查 ·
            确认门仅工作台 UI,agent 不可代确认
          </div>
        </div>
        <div className="ph-actions">
          {st ? (
            <span className={`pill ${STATUS_PILL_CLASS[st.tone]}`}>
              {st.tone === "warn" ? (
                <span className="dot dot-warn" aria-hidden />
              ) : null}
              {st.label}
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => {
              void taskQuery.refetch();
              void baselinesQuery.refetch();
            }}
            disabled={taskQuery.isFetching || baselinesQuery.isFetching}
          >
            刷新
          </button>
        </div>
      </div>

      {/* 页顶警示(原型 s4 卡点语义):基准错误将批量产生错误结论 */}
      <div className="note-bar warnbar">
        <svg className="ic" viewBox="0 0 24 24" aria-hidden>
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
        <span>基准错误将批量产生错误结论——逐条核对后再确认。</span>
      </div>

      {taskQuery.isError ? (
        <div className="note-bar errbar">
          <svg className="ic" viewBox="0 0 24 24" aria-hidden>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          <span style={{ flex: 1 }}>
            任务加载失败:{taskQuery.error.message}
          </span>
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void taskQuery.refetch()}
          >
            重试
          </button>
        </div>
      ) : null}

      {/* ── 解析质量表已迁 /parsing 归拢专屏(Plan6,spec §4.3;
          bid-review-parsing.dom.test.tsx 接管断言)── */}

      {/* ── 字段对照 + 确认(s4 一期;baselines 行级快照)────────────── */}
      <div className="gate1-card">
        <div className="gate1-hd">
          <div className="gate1-badge">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden>
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
          </div>
          <div>
            <h3>基准字段对照</h3>
            <div className="hd-sub">
              引擎从材料中抽取的基准快照——审查即以此为准;冲突取值需人工裁定,
              置信 pill 以 quote 原文核验为准
            </div>
          </div>
        </div>

        {baselinesQuery.isPending ? (
          <div style={{ padding: "0 16px 14px" }}>
            <div className="f-card">
              <div className="f-hd">
                <span className="f-path">基线加载中…</span>
              </div>
              <div className="f-src">正在读取基线字段快照。</div>
            </div>
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "0 16px 14px" }}>
            <div className="note-bar" style={{ marginTop: 0 }}>
              <svg className="ic" viewBox="0 0 24 24" aria-hidden>
                <circle cx="12" cy="12" r="10" />
                <path d="M12 16v-4M12 8h.01" />
              </svg>
              <span>
                基线尚未生成——任务完成字段抽取后此处显示基准快照
                (created/解析中状态属正常)。
              </span>
            </div>
          </div>
        ) : (
          <div style={{ padding: "0 16px 14px" }}>
            <div
              style={{
                fontSize: 12,
                color: "var(--text-3)",
                marginBottom: 8,
              }}
            >
              共 <span className="num">{allRows.length}</span> 字段 · 已抽取{" "}
              <span className="num">{allRows.length - missingTotal}</span> ·
              缺失 <span className="num">{missingTotal}</span>
              {conflictPaths.length > 0 ? (
                <>
                  {" "}
                  · 冲突 <span className="num">{conflictPaths.length}</span>
                  {unresolvedCount > 0
                    ? `(未裁 ${unresolvedCount})`
                    : "(已全裁定)"}
                </>
              ) : null}{" "}
              · 快照哈希{" "}
              <code className="k">
                {(rows[0]?.materials_hash ?? "").slice(0, 12) || "—"}
              </code>
            </div>
            {/* ── 冲突裁定卡(二期 spec §1.5):多候选 radio + 采纳 → adjudicate;已裁定转pill ── */}
            {conflictPaths.length > 0 ? (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  marginBottom: 12,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  冲突待裁定 <span className="num">{conflictPaths.length}</span>
                  处——同一字段在材料中取到多个不一致候选,采纳后写入基准
                </div>
                {conflictPaths.map((p) => {
                  const cands = conflictCands[p] ?? [];
                  const adj = adjudications[p];
                  return (
                    <div className="f-card pend" key={p}>
                      <div className="f-hd">
                        <span className="f-path" title={p}>
                          {labels[p] ?? p}
                          <code
                            className="k"
                            style={{ marginLeft: 6, fontSize: 11 }}
                          >
                            {p}
                          </code>
                        </span>
                        {adj ? (
                          <span className="pill pill-ok">已裁定</span>
                        ) : (
                          <span className="pill pill-warn">待裁定</span>
                        )}
                      </div>
                      <div
                        role="radiogroup"
                        aria-label={`裁定 ${labels[p] ?? p}`}
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 4,
                          margin: "8px 0",
                        }}
                      >
                        {cands.map((c, i) => {
                          const isAdjValue =
                            adj != null &&
                            JSON.stringify(c.value) ===
                              JSON.stringify(adj.value);
                          return (
                            <label
                              key={i}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 6,
                                fontSize: 13,
                                cursor: gateOpen ? "pointer" : "default",
                              }}
                            >
                              <input
                                type="radio"
                                name={`cand-${p}`}
                                checked={picks[p] === i || isAdjValue}
                                disabled={!gateOpen}
                                onChange={() =>
                                  setPicks((m) => ({ ...m, [p]: i }))
                                }
                              />
                              <span>{formatVal(c.value)}</span>
                              <span
                                style={{
                                  color: "var(--text-3)",
                                  fontSize: 12,
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                                title={`${c.doc_id}${c.page != null ? ` · p.${c.page}` : ""}${c.quote ? ` ·「${c.quote}」` : ""}`}
                              >
                                {c.doc_id}
                                {c.page != null ? ` · p.${c.page}` : ""}
                                {c.quote ? ` ·「${c.quote}」` : ""}
                              </span>
                            </label>
                          );
                        })}
                        {cands.length === 0 ? (
                          <span
                            style={{ fontSize: 12, color: "var(--text-3)" }}
                          >
                            候选清单缺失(旧快照)——可重跑字段抽取后再裁定。
                          </span>
                        ) : null}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          flexWrap: "wrap",
                        }}
                      >
                        <button
                          type="button"
                          className="btn btn-pri btn-sm"
                          disabled={
                            !gateOpen ||
                            picks[p] == null ||
                            adjudicate.isPending
                          }
                          onClick={() => {
                            const i = picks[p];
                            const c = i != null ? cands[i] : undefined;
                            if (!c) return;
                            adjudicate.mutate(
                              { path: p, value: c.value },
                              {
                                onSuccess: () =>
                                  toast.success(
                                    `已采纳「${formatVal(c.value)}」为 ${labels[p] ?? p} 的基准值`,
                                  ),
                                onError: (e) =>
                                  toast.error(
                                    e instanceof Error ? e.message : "裁定失败",
                                  ),
                              },
                            );
                          }}
                        >
                          采纳为基准值
                        </button>
                        {adj ? (
                          <span
                            style={{
                              fontSize: 12,
                              color: "var(--text-3)",
                            }}
                          >
                            当前基准 {formatVal(adj.value)} · 裁定于{" "}
                            {adj.at.slice(0, 16).replace("T", " ")}
                          </span>
                        ) : null}
                        {!gateOpen ? (
                          <span
                            style={{ fontSize: 12, color: "var(--text-3)" }}
                          >
                            仅待确认状态可裁定
                          </span>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : null}
            <div className="split">
              <div className="card" style={{ overflow: "hidden" }}>
                <div className="fam-search">
                  <input
                    className="inp"
                    placeholder="按字段路径过滤…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    aria-label="按字段路径过滤"
                  />
                </div>
                <div className="fam-list">
                  {FAMILIES.filter((f) => famStats.has(f.key)).map((f) => {
                    const stat = famStats.get(f.key);
                    return (
                      <button
                        type="button"
                        key={f.key}
                        className={`fam-item ${famKey === f.key ? "on" : ""}`}
                        onClick={() => setFam(f.key)}
                      >
                        {f.label}
                        {(stat?.missing ?? 0) > 0 ? (
                          <span className="mini-dot" aria-hidden />
                        ) : null}
                        <span className="fam-cnt">
                          {stat ? stat.total - stat.missing : 0}/
                          {stat?.total ?? 0}
                        </span>
                      </button>
                    );
                  })}
                  {[...famStats.keys()]
                    .filter((k) => !FAMILIES.some((f) => f.key === k))
                    .map((k) => {
                      const stat = famStats.get(k);
                      return (
                        <button
                          type="button"
                          key={k}
                          className={`fam-item ${famKey === k ? "on" : ""}`}
                          onClick={() => setFam(k)}
                        >
                          {k}
                          <span className="fam-cnt">
                            {stat ? stat.total - stat.missing : 0}/
                            {stat?.total ?? 0}
                          </span>
                        </button>
                      );
                    })}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  minWidth: 0,
                }}
              >
                {shown.map((f) => {
                  const src = f.src;
                  return (
                    <div
                      className={`f-card ${f.missing ? "pend" : ""}`}
                      key={f.path}
                    >
                      <div className="f-hd">
                        <span className="f-path" title={f.path}>
                          {f.label}
                          {f.label !== f.path ? (
                            <code
                              className="k"
                              style={{ marginLeft: 6, fontSize: 11 }}
                            >
                              {f.path}
                            </code>
                          ) : null}
                        </span>
                        <span style={{ display: "flex", gap: 4 }}>
                          {!f.missing && !f.conflicted ? (
                            <span className={`pill ${confPill(f.conf).cls}`}>
                              {confPill(f.conf).text}
                            </span>
                          ) : null}
                          <span
                            className={`pill ${f.missing ? "pill-warn" : "pill-ok"}`}
                          >
                            {f.missing
                              ? "缺失"
                              : f.conflicted
                                ? "冲突"
                                : "已抽取"}
                          </span>
                        </span>
                      </div>
                      <div className="f-val">{formatVal(f.value)}</div>
                      <div className="f-src">
                        {src ? (
                          <>
                            <span>
                              来源 {src.doc_id}
                              {src.page != null ? ` · p.${src.page}` : ""}
                            </span>
                            {src.quote ? (
                              <span
                                style={{
                                  maxWidth: 420,
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                                title={src.quote}
                              >
                                「{src.quote}」
                              </span>
                            ) : null}
                            <button
                              type="button"
                              className="src-chip src-chip-btn"
                              onClick={() =>
                                setLocate({
                                  docId: src.doc_id,
                                  page: src.page,
                                  quote: src.quote,
                                })
                              }
                            >
                              查看原文
                            </button>
                          </>
                        ) : (
                          <span>
                            {f.missing
                              ? "未在材料中定位到该字段——若招标有要求而投标未提供,构成响应缺失(废标风险)"
                              : "无出处记录(引擎未回传 provenance)"}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
                {shown.length === 0 ? (
                  <div className="f-card">
                    <div className="f-hd">
                      <span className="f-path">无匹配字段</span>
                    </div>
                    <div className="f-src">调整检索词或切换字段族。</div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 确认门置底(gate-bar,原型 s4);点击触发后端 409 收紧逻辑 */}
      <div className="gate-bar">
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            基准确认进度{" "}
            <span className="num">
              {gateOpen
                ? `0%(待确认${unconfirmedRows > 0 ? ` · ${unconfirmedRows} 行未确认` : ""}${unresolvedCount > 0 ? ` · ${unresolvedCount} 处冲突未裁定` : ""})`
                : task
                  ? "100%(已过确认门)"
                  : "—"}
            </span>
          </div>
          <div className="g-info">
            {gateOpen
              ? "卡点:基准确认前任务停留在待确认状态,不进入审查;确认后任务续跑(running→审查完成)。"
              : task
                ? "任务已过确认门,审查继续;改错可回到本页重新确认。"
                : "当前状态无待确认基线(仅 awaiting_confirm 状态可确认)。"}
          </div>
        </div>
        <span className="meter" style={{ width: 120 }}>
          <i style={{ width: `${gatePct}%` }} />
        </span>
        <button
          type="button"
          className="btn btn-pri"
          disabled={!gateOpen || confirm.isPending}
          onClick={() =>
            confirm.mutate(taskId, {
              onSuccess: () => toast.success("基线已确认,审查续跑中"),
            })
          }
        >
          {confirm.isPending
            ? "确认中…"
            : gateOpen && unconfirmedRows + unresolvedCount > 0
              ? `确认基准包并开始审查(待确认 ${unconfirmedRows} 行${unresolvedCount > 0 ? ` · 未裁定冲突 ${unresolvedCount} 处` : ""})`
              : "确认基准包并开始审查"}
        </button>
      </div>

      {/* 定位原文 modal(字段卡「查看原文」→ 溯源取数端点,与工作台证据 chip 同源) */}
      {locate ? (
        <DocLocateModal
          taskId={taskId}
          target={locate}
          onClose={() => setLocate(null)}
        />
      ) : null}
    </div>
  );
}
