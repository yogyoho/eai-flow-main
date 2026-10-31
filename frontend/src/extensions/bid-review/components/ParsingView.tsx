"use client";

/**
 * 解析与字段抽取专屏(原型 s3;spec §4.3,UX 重构 Plan6)。
 * EAI-CUSTOM (2026-10-31): 归拢散落 4 处的解析只读信息——
 * ① 页头四元组(业务号=TaskTitleTag · 项目/标段 · 模式)+ 待基准确认 pill
 *   (状态驱动,awaiting_confirm 才显);
 * ② 六步步骤条+引擎进度行(共享 TaskStepper,canonical home 在此);
 * ③ 解析质量表(自 BaselineView gate1 卡迁入;B3 页级置信落地前无「识别置信度」
 *   列,维持文档级 OCR 注记=诚实降级);
 * ④ 基准字段对照只读区(自 BaselineView 字段族区迁入只读部分:汇总行+族 tabs+
 *   字段卡;冲突不嵌裁定 radio——给「去基准确认」链接,裁定交互仍留基准确认页)。
 * 资料完备性卡迁 /results(M3,spec §4.5),不在本屏。
 * 数据面:useBidTask + useBidBaselines(与基准确认页同源同词汇)。
 */

import { AlertTriangle, Layers } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { type LocateTarget } from "@/extensions/bid-review/api";
// 共享词汇(baselineFields,Plan6 与 BaselineView 同源)
import {
  type DocMeta,
  FAMILIES,
  familyOf,
  NO_LABELS,
  STATUS_PILL_CLASS,
  confPill,
  fieldRows,
  formatVal,
  KIND_LABEL,
  roleLabel,
  rolePillClass,
} from "@/extensions/bid-review/components/baselineFields";
import { DocLocateModal } from "@/extensions/bid-review/components/DocLocateModal";
import { taskStatusPill } from "@/extensions/bid-review/components/primitives";
import { TaskStepper } from "@/extensions/bid-review/components/TaskStepper";
import { TaskTitleTag } from "@/extensions/bid-review/components/TaskTitleTag";
import { useBidBaselines, useBidTask } from "@/extensions/bid-review/hooks";

export function ParsingView({ taskId }: { taskId?: string | null }) {
  const taskQuery = useBidTask(taskId ?? null);
  const baselinesQuery = useBidBaselines(taskId ?? null);

  const task = taskQuery.data ?? null;
  const data = baselinesQuery.data;
  const rows = useMemo(() => data?.items ?? [], [data]);
  const labels = data?.labels ?? NO_LABELS;
  const adjudications = data?.adjudications ?? {};
  const [fam, setFam] = useState<string>("tender");
  const [search, setSearch] = useState("");
  const [locate, setLocate] = useState<LocateTarget | null>(null);

  // 解析质量数据 = engine_meta.docs 清单(同 BaselineView 口径)
  const docs = Array.isArray(task?.engine_meta?.docs)
    ? (task.engine_meta.docs as DocMeta[])
    : [];
  const ocrDocs = docs.filter((d) => (d.assets ?? 0) > 0);

  // 派生(与 BaselineView 同公式;冲突只读展示,裁定在基准确认页)
  const conflictPaths = useMemo(() => {
    const all = new Set<string>();
    for (const r of rows) for (const p of r.conflicts ?? []) all.add(p);
    return [...all].sort();
  }, [rows]);
  const unresolvedCount = conflictPaths.filter(
    (p) => adjudications[p] === undefined,
  ).length;
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

  const baselineUnconfirmed = task?.status === "awaiting_confirm";
  const st = task ? taskStatusPill(task.status) : null;
  const modeLabel = task?.mode === "deep" ? "深度评审" : "快速审查";
  const identity = [task?.project_name, task?.lot_name]
    .filter(Boolean)
    .join(" / ");

  if (!taskId) {
    return (
      <div className="screen on">
        <div className="page-head">
          <div className="ph-icon">
            <Layers className="ic" />
          </div>
          <div>
            <h2>解析与字段抽取</h2>
            <div className="ph-sub">引擎解析与基准快照的只读归拢视图</div>
          </div>
        </div>
        <div className="note-bar warnbar">
          <AlertTriangle className="ic" />
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

  return (
    <div className="screen on">
      {/* ── 页头四元组 + 待基准确认 pill ── */}
      <div className="page-head">
        <div className="ph-icon">
          <Layers className="ic" />
        </div>
        <div>
          <h2>
            解析与字段抽取
            <TaskTitleTag taskId={taskId} bizNo={task?.biz_no} />
          </h2>
          <div className="ph-sub">
            {identity ? `${identity} · ` : ""}
            {task ? modeLabel : "任务详情加载中…"}
          </div>
        </div>
        <div className="ph-actions">
          {baselineUnconfirmed ? (
            <span className="pill pill-orange">
              <span className="dot dot-warn" />
              待基准确认
            </span>
          ) : null}
          {st ? (
            <span className={`pill ${STATUS_PILL_CLASS[st.tone]}`}>
              {st.label}
            </span>
          ) : null}
        </div>
      </div>

      {/* 审查失败:引擎错误原样注记 */}
      {task?.status === "failed" ? (
        <div
          className="note-bar errbar"
          style={{ marginTop: 0, marginBottom: 12 }}
        >
          <AlertTriangle className="ic" />
          <span>审查失败:{task.error ?? "未知错误"}</span>
        </div>
      ) : null}

      {/* ── 六步步骤条 + 引擎进度行(共享件,canonical home 在此) ── */}
      <TaskStepper task={task} />

      {/* ── 解析质量表(原型 s3;自 BaselineView gate1 卡迁入)── */}
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

      {/* ── 基准字段对照只读区(自 BaselineView 字段族区迁入;冲突链接化)── */}
      <div className="gate1-card">
        <div className="gate1-hd">
          <div className="gate1-badge">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden>
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
          </div>
          <div>
            <h3>基准字段抽取</h3>
            <div className="hd-sub">
              引擎从材料中抽取的基准快照——审查即以此为准;冲突取值需在基准确认页人工裁定
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
            {/* 冲突只读注记(spec §4.3):不嵌裁定 radio——去基准确认页裁定 */}
            {conflictPaths.length > 0 ? (
              <div className="note-bar warnbar" style={{ marginBottom: 12 }}>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden>
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                  <path d="M12 9v4M12 17h.01" />
                </svg>
                <span style={{ flex: 1 }}>
                  冲突待裁定{" "}
                  <span className="num">{conflictPaths.length}</span>
                  处——同一字段在材料中取到多个不一致候选,需人工裁定后写入基准。
                </span>
                <Link
                  href={`/bid-review/baseline?task_id=${taskId}`}
                  className="btn btn-sec btn-sm"
                >
                  去基准确认 →
                </Link>
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
            {/* 三值语义防误读(spec §4.3):缺失≠通过,冲突以裁定为准 */}
            <div className="tbl-foot">
              缺失字段按 need_human 语义处理——不阻断审查,也不计为通过;冲突字段以基准确认页人工裁定结果为准。
            </div>
          </div>
        )}
      </div>

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
