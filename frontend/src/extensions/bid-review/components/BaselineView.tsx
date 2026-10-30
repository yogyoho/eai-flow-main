"use client";

/**
 * 基准确认页(bid:page:baseline)。
 * EAI-CUSTOM (2026-10-30): 参照 docs/designs/2026-10-30-bid-review-ui.html 原型
 * s3(解析与字段抽取)/s4(基准确认卡点),在同一路由分区呈现:
 * - 解析质量表(s3 一期):engine_meta.docs 清单(kind/pages/chars/assets/status,
 *   pdf 真页码、docx 无页边界诚实 0→「—」;assets>0 行注 OCR 兜底);
 * - 字段对照(s3/s4 一期):GET /tasks/{id}/baselines 行级快照(routers
 *   list_task_baselines,分期建议一期落地)→ 按首段路径族(tender/bid)分组,
 *   字段卡只读核对(值/出处/「查看原文」定位弹层);冲突裁定/置信度/锚点=
 *   引擎二期缺口,挂账不伪造(routers 端点注释同记)。
 * 类词汇表=app/bid-review/bid-review.css(.brx 词汇:.tbl/.split/fam- 系列/.f-card/.gate-bar)。
 * 行为契约不变:useBidTask 详情 + useBidConfirmTask 确认门;仅 awaiting_confirm 可确认
 * (gateOpen gating);409(ApiError.status)分流 toast「存在未复核致命项」照旧。
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  type BidBaselineRow,
  type LocateTarget,
  ApiError,
} from "@/extensions/bid-review/api";
import { DocLocateModal } from "@/extensions/bid-review/components/DocLocateModal";
import { taskStatusPill } from "@/extensions/bid-review/components/primitives";
import {
  useBidBaselines,
  useBidConfirmTask,
  useBidTask,
} from "@/extensions/bid-review/hooks";
import { type PillTone } from "@/extensions/contract-price/components/ui/bits";

interface DocMeta {
  doc_id?: string;
  role?: string;
  kind?: string;
  pages?: number;
  chars?: number;
  assets?: number;
  status?: string;
  /** v1 旧任务(上传即解码纯文本直存)遗留字段,仅用于字符数回退估算。 */
  text?: string;
}

const KIND_LABEL: Record<string, string> = {
  docx: "Word",
  pdf: "PDF",
  text: "文本",
};

function roleLabel(role: string | undefined): string {
  if (role === "tender") return "招标";
  if (role === "bid") return "投标";
  return role ?? "未知";
}

/** role → 原型 pill 档(招标=主色/投标=橙警示/未知=灰)。 */
function rolePillClass(role: string | undefined): string {
  if (role === "tender") return "pill-main";
  if (role === "bid") return "pill-orange";
  return "pill-gray";
}

/** taskStatusPill 的 PillTone → 原型 .pill-* 档(info 无专属档,归主色)。 */
const STATUS_PILL_CLASS: Record<PillTone, string> = {
  primary: "pill-main",
  success: "pill-ok",
  warn: "pill-warn",
  error: "pill-err",
  gray: "pill-gray",
  info: "pill-main",
};

/** 字段族:路径首段(tender/bid);一期限引擎语义,主题级中文分组待标签映射。 */
const FAMILIES: { key: string; label: string }[] = [
  { key: "tender", label: "招标基准" },
  { key: "bid", label: "投标响应" },
];

function familyOf(path: string): string {
  return path.split(".", 1)[0] ?? path;
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toLocaleString();
  if (typeof v === "boolean") return v ? "是" : "否";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

/** 单行基线快照 → 字段卡列表数据(行间快照同源,取首行即可)。 */
function fieldRows(row: BidBaselineRow | undefined) {
  const fields = row?.fields ?? {};
  const prov = row?.provenance ?? {};
  const paths = Object.keys(fields).sort();
  return paths.map((p) => {
    const value = fields[p];
    const src = prov[p];
    return {
      path: p,
      value,
      missing: value === null || value === undefined,
      src,
    };
  });
}

export function BaselineView({ taskId }: { taskId?: string | null }) {
  const taskQuery = useBidTask(taskId ?? null);
  const baselinesQuery = useBidBaselines(taskId ?? null);
  const confirm = useBidConfirmTask();

  const task = taskQuery.data ?? null;
  const gateOpen = task?.status === "awaiting_confirm";
  const rows = useMemo(() => baselinesQuery.data ?? [], [baselinesQuery.data]);
  const [fam, setFam] = useState<string>("tender");
  const [search, setSearch] = useState("");
  const [locate, setLocate] = useState<LocateTarget | null>(null);

  // 解析质量数据 = engine_meta.docs 清单(解析层落;v1 旧任务仅有 doc_id/role/text)
  const docs = Array.isArray(task?.engine_meta?.docs)
    ? (task.engine_meta.docs as DocMeta[])
    : [];
  const ocrDocs = docs.filter((d) => (d.assets ?? 0) > 0);

  // 字段族计数(全快照口径,不随筛选变);检索只过滤当前族展示
  const allRows = useMemo(() => fieldRows(rows[0]), [rows]);
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
      const err = confirm.error;
      // 确认门 409 → toast「存在未复核致命项」(spec §3.2/§3.3;Task 15 收紧落地即生效)
      toast.error(
        err instanceof ApiError && err.status === 409
          ? "存在未复核致命项"
          : (err?.message ?? "确认失败"),
      );
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
  // 进度按确认门状态位(逐字段勾选核对=原型 ck-pend,依赖冲突裁定,二期挂账)
  const gatePct = gateOpen ? 0 : task ? 100 : 0;
  const unconfirmedRows = rows.filter((r) => !r.confirmed).length;

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
          <h2>招标基准确认</h2>
          <div className="ph-sub">
            任务 {taskId.slice(0, 8)} · 确认招标要求——未完成将不能开始审查 ·
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

      {/* ── 解析质量表(原型 s3 一期;数据=解析层 engine_meta.docs 清单)── */}
      <div className="gate1-card" style={{ marginTop: 12 }}>
        <div className="gate1-hd">
          <div className="gate1-badge">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
            </svg>
          </div>
          <div>
            <h3>解析质量</h3>
            <div className="hd-sub">
              机器读了什么——上传材料解析清单(docx 无页边界,页数以「—」示)
            </div>
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>文件</th>
                <th>角色</th>
                <th>类型</th>
                <th className="r">页数</th>
                <th className="r">字符</th>
                <th className="r">图片/扫描页</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {docs.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ color: "var(--text-3)" }}>
                    {taskQuery.isPending ? "任务加载中…" : "该任务无上传材料"}
                  </td>
                </tr>
              ) : (
                docs.map((d, idx) => (
                  <tr key={`${d.doc_id ?? "doc"}-${idx}`}>
                    <td className="mono" title={d.doc_id}>
                      {d.doc_id ?? "—"}
                    </td>
                    <td>
                      <span className={`pill ${rolePillClass(d.role)}`}>
                        {roleLabel(d.role)}
                      </span>
                    </td>
                    <td>{KIND_LABEL[d.kind ?? ""] ?? d.kind ?? "文本"}</td>
                    <td className="r num">
                      {(d.pages ?? 0) > 0 ? d.pages : "—"}
                    </td>
                    <td className="r num">
                      {d.chars != null && d.chars > 0
                        ? d.chars.toLocaleString()
                        : typeof d.text === "string"
                          ? d.text.length.toLocaleString()
                          : "—"}
                    </td>
                    <td className="r num">{d.assets ?? 0}</td>
                    <td>
                      <span
                        className={`pill ${
                          d.status === "parsed" ? "pill-ok" : "pill-warn"
                        }`}
                      >
                        {d.status === "parsed"
                          ? "已解析"
                          : (d.status ?? "待解析")}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {ocrDocs.length > 0 ? (
          <div className="drawer-ft">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden>
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4M12 8h.01" />
            </svg>
            <span>
              {ocrDocs.length} 份文档含扫描页/内嵌图片,已 OCR
              转写并入检索文本(转写可能有误,字段核对时留意)。
            </span>
          </div>
        ) : null}
      </div>

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
              引擎从材料中抽取的基准快照——审查即以此为准;冲突裁定/置信度为引擎
              二期能力,当前缺失字段如实标注
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
              缺失 <span className="num">{missingTotal}</span> · 快照哈希{" "}
              <code className="k">
                {(rows[0]?.materials_hash ?? "").slice(0, 12) || "—"}
              </code>
            </div>
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
                        <span className="f-path">{f.path}</span>
                        <span
                          className={`pill ${f.missing ? "pill-warn" : "pill-ok"}`}
                        >
                          {f.missing ? "缺失" : "已抽取"}
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
                ? `0%(待确认${unconfirmedRows > 0 ? ` · ${unconfirmedRows} 行未确认` : ""})`
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
            : gateOpen && unconfirmedRows > 0
              ? `确认基准包并开始审查(待确认 ${unconfirmedRows} 行)`
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
