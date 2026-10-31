"use client";

/**
 * 解析与字段抽取专屏(原型 s3;spec §4.3,UX 重构 Plan6)。
 * EAI-CUSTOM (2026-10-31): 归拢散落 4 处的解析只读信息——
 * ① 页头四元组(业务号=TaskTitleTag · 项目/标段 · 模式)+ 待基准确认 pill
 *   (状态驱动,awaiting_confirm 才显);
 * ② 六步步骤条+引擎进度行(共享 TaskStepper,canonical home 在此);
 * ③ 解析质量卡 = 原型 s3 扁平 5 列表(文件/页数/识别置信度/状态/说明)+ OCR
 *   兜底整行;B3 页级置信未落地 → 置信格「—」诚实降级,OCR 注记走兜底行,
 *   不伪造页码区间/置信数字;
 * ④ 基准字段抽取卡 = 原型 s3 扁平表+说明列(字段路径/说明/锚点/抽取值/形态/
 *   状态;2026-10-31 用户要求:说明列=labels 中文名,无 label 段翻译
 *   bid.total_price→投标.总价)+hd-right 三 pill(已抽取/冲突/缺失)+
 *   tbl-foot on_missing_input 注。
 *   裁定 15(2026-10-31 用户纠正):本屏不用基准确认页的字段族 tabs/字段卡
 *   交互形态——归拢只读屏用表,裁定交互仍留基准确认页(冲突行只给候选
 *   pill+「去基准确认」链接,不嵌 radio)。
 * 资料完备性卡迁 /results(M3,spec §4.5),不在本屏。
 * 数据面:useBidTask + useBidBaselines(与基准确认页同源同词汇)。
 */

import { AlertTriangle, Layers } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  type BidCandidate,
  type LocateTarget,
} from "@/extensions/bid-review/api";
// 共享词汇(baselineFields,Plan6 与 BaselineView 同源)
import {
  type DocMeta,
  NO_LABELS,
  STATUS_PILL_CLASS,
  fieldRows,
  formatVal,
  pathZh,
} from "@/extensions/bid-review/components/baselineFields";
import { DocLocateModal } from "@/extensions/bid-review/components/DocLocateModal";
import { taskStatusPill } from "@/extensions/bid-review/components/primitives";
import { TaskStepper } from "@/extensions/bid-review/components/TaskStepper";
import { TaskTitleTag } from "@/extensions/bid-review/components/TaskTitleTag";
import { useBidBaselines, useBidTask } from "@/extensions/bid-review/hooks";

/** 形态列(原型 s3):从值类型派生——string/number/bool/list/object;缺失「—」。 */
function shapeOf(v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) return "list";
  if (typeof v === "object") return "object";
  if (typeof v === "boolean") return "bool";
  return typeof v;
}

// 客户端分页(2026-10-31 用户要求;与 WorkbenchView issues 同词汇):每页 10 行,
// 页状态各自独立,越界页码收敛(数据重取后变少不空白),切任务经 key 重置。
const PAGE_SIZE = 10;

function Pager(props: {
  total: number;
  label: string;
  page: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (props.totalPages <= 1) return null;
  return (
    <div className="tbl-foot">
      <span>
        共 {props.total} {props.label}
      </span>
      <span style={{ flex: 1 }} />
      <button
        type="button"
        className="btn btn-sec btn-sm"
        disabled={props.page <= 1}
        onClick={props.onPrev}
      >
        上一页
      </button>
      <span className="num">
        第 {props.page} / {props.totalPages} 页
      </span>
      <button
        type="button"
        className="btn btn-sec btn-sm"
        disabled={props.page >= props.totalPages}
        onClick={props.onNext}
      >
        下一页
      </button>
    </div>
  );
}

export function ParsingView({ taskId }: { taskId?: string | null }) {
  const taskQuery = useBidTask(taskId ?? null);
  const baselinesQuery = useBidBaselines(taskId ?? null);

  const task = taskQuery.data ?? null;
  const data = baselinesQuery.data;
  const rows = useMemo(() => data?.items ?? [], [data]);
  const labels = data?.labels ?? NO_LABELS;
  const adjudications = data?.adjudications ?? {};
  const [locate, setLocate] = useState<LocateTarget | null>(null);

  // 解析质量数据 = engine_meta.docs 清单(原型 s3:文件/页数/置信度/状态/说明)
  const docs = Array.isArray(task?.engine_meta?.docs)
    ? (task.engine_meta.docs as DocMeta[])
    : [];
  const totalPages = docs.reduce((s, d) => s + (d.pages ?? 0), 0);
  const ocrDocs = docs.filter((d) => (d.assets ?? 0) > 0);

  // 派生(与 BaselineView 同公式;冲突只读展示,裁定在基准确认页)
  const conflictPaths = useMemo(() => {
    const all = new Set<string>();
    for (const r of rows) for (const p of r.conflicts ?? []) all.add(p);
    return [...all].sort();
  }, [rows]);
  const candidates = useMemo(() => {
    const m: Record<string, BidCandidate[]> = {};
    for (const r of rows)
      for (const [p, c] of Object.entries(r.candidates ?? {})) m[p] = c;
    return m;
  }, [rows]);
  const allRows = useMemo(() => fieldRows(rows[0], labels), [rows, labels]);
  const missingTotal = allRows.filter((f) => f.missing).length;
  const hash12 = (rows[0]?.materials_hash ?? "").slice(0, 12) || "—";

  // 两表分页状态(独立;safePage 收敛越界)
  const [docPage, setDocPage] = useState(1);
  const [fieldPage, setFieldPage] = useState(1);
  const docTotalPages = Math.max(1, Math.ceil(docs.length / PAGE_SIZE));
  const docSafe = Math.min(docPage, docTotalPages);
  const fieldTotalPages = Math.max(1, Math.ceil(allRows.length / PAGE_SIZE));
  const fieldSafe = Math.min(fieldPage, fieldTotalPages);
  const shownDocs = docs.slice((docSafe - 1) * PAGE_SIZE, docSafe * PAGE_SIZE);
  const shownFields = allRows.slice(
    (fieldSafe - 1) * PAGE_SIZE,
    fieldSafe * PAGE_SIZE,
  );

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

      {/* ── 解析质量(原型 s3:扁平 5 列表+OCR 兜底行)── */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-hd">
          <h3>解析质量</h3>
          <span className="hd-sub">
            {docs.length} 个文件 · {totalPages} 页
          </span>
          {/* 低置信页 pill:B3 页级置信落地后接入(hd-right) */}
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>文件</th>
                <th className="r">页数</th>
                <th>识别置信度</th>
                <th>状态</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {docs.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ color: "var(--text-3)" }}>
                    {taskQuery.isPending ? "任务加载中…" : "该任务无上传材料"}
                  </td>
                </tr>
              ) : (
                <>
                  {shownDocs.map((d, idx) => (
                    <tr key={`${d.doc_id ?? "doc"}-${idx}`}>
                      <td className="mono" title={d.doc_id}>
                        {d.doc_id ?? "—"}
                      </td>
                      <td className="r num">
                        {(d.pages ?? 0) > 0 ? d.pages : "—"}
                      </td>
                      {/* B3 页级置信未落地:不冒充数字,「—」+悬停说明 */}
                      <td
                        style={{ color: "var(--text-3)" }}
                        title="页级识别置信度待引擎 B3 能力落地后提供"
                      >
                        —
                      </td>
                      <td>
                        <span
                          className={`pill ${
                            d.status === "parsed" ? "pill-ok" : "pill-warn"
                          }`}
                        >
                          {d.status === "parsed"
                            ? "完成"
                            : (d.status ?? "待解析")}
                        </span>
                      </td>
                      <td style={{ color: "var(--text-3)" }}>
                        {d.kind === "docx" ? "docx 无页边界" : "—"}
                      </td>
                    </tr>
                  ))}
                  {shownDocs
                    .filter((d) => (d.assets ?? 0) > 0)
                    .map((d, idx) => (
                      <tr key={`ocr-${d.doc_id ?? idx}`}>
                        <td
                          colSpan={5}
                          style={{ background: "var(--warn-50)" }}
                        >
                          <span className="pill pill-warn">OCR 兜底</span>&nbsp;{" "}
                          {d.doc_id} 含 <b className="num">{d.assets}</b>{" "}
                          个扫描页/内嵌图片——已 OCR
                          转写并入检索文本,对应字段抽取值请留意人工核对
                        </td>
                      </tr>
                    ))}
                </>
              )}
            </tbody>
          </table>
        </div>
        <Pager
          key={`doc-${taskId}`}
          total={docs.length}
          label="个文件"
          page={docSafe}
          totalPages={docTotalPages}
          onPrev={() => setDocPage(docSafe - 1)}
          onNext={() => setDocPage(docSafe + 1)}
        />
      </div>

      {/* ── 基准字段抽取(原型 s3:扁平 5 列表+hd-right 三 pill;裁定 15)── */}
      <div className="card">
        <div className="card-hd">
          <h3>基准字段抽取</h3>
          <span className="hd-sub">
            按字段路径对照 · 快照 <code className="k">{hash12}</code>
          </span>
          <div className="hd-right">
            <span className="pill pill-ok">
              已抽取 {allRows.length - missingTotal}
            </span>
            <span className="pill pill-warn">冲突 {conflictPaths.length}</span>
            <span className="pill pill-gray">缺失 {missingTotal}</span>
          </div>
        </div>

        {baselinesQuery.isPending ? (
          <div className="tbl-foot">基线字段快照加载中…</div>
        ) : rows.length === 0 ? (
          <div className="tbl-foot">
            基线尚未生成——任务完成字段抽取后此处显示基准快照
            (created/解析中状态属正常)。
          </div>
        ) : (
          <>
            {/* 冲突只读注记(spec §4.3):不嵌裁定 radio——去基准确认页裁定 */}
            {conflictPaths.length > 0 ? (
              <div
                className="note-bar warnbar"
                style={{ margin: "0 16px 12px" }}
              >
                <AlertTriangle className="ic" />
                <span style={{ flex: 1 }}>
                  冲突待裁定 <span className="num">{conflictPaths.length}</span>
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
            <div style={{ overflowX: "auto" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>字段路径</th>
                    <th>说明</th>
                    <th>锚点</th>
                    <th>抽取值</th>
                    <th>形态</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {shownFields.map((f) => {
                    const cands = candidates[f.path] ?? [];
                    const cand0 = cands[0];
                    const src = f.src;
                    return (
                      <tr key={f.path}>
                        <td className="mono" title={f.label}>
                          {f.path}
                        </td>
                        <td>{pathZh(f.path, f.label)}</td>
                        <td>
                          {src ? (
                            <>
                              <code className="k">
                                {src.doc_id}
                                {src.page != null ? ` · p.${src.page}` : ""}
                              </code>{" "}
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
                          ) : f.missing ? (
                            <span style={{ color: "var(--text-3)" }}>
                              未在正文定位到
                            </span>
                          ) : (
                            <span
                              style={{ color: "var(--text-3)" }}
                              title="引擎未回传 provenance"
                            >
                              —
                            </span>
                          )}
                        </td>
                        <td>
                          {f.missing ? (
                            <span style={{ color: "var(--text-3)" }}>
                              未在正文定位到
                            </span>
                          ) : (
                            <span
                              className={
                                typeof f.value === "number" ? "num" : undefined
                              }
                            >
                              {formatVal(f.value)}
                            </span>
                          )}
                          {f.conflicted ? (
                            <span
                              className="pill pill-warn"
                              style={{
                                height: 18,
                                fontSize: 11,
                                marginLeft: 6,
                              }}
                            >
                              {cand0 != null
                                ? `候选 ${formatVal(cand0.value)}`
                                : "冲突待裁定"}
                            </span>
                          ) : null}
                        </td>
                        <td className="mono">{shapeOf(f.value)}</td>
                        <td>
                          <span
                            className={`pill ${
                              f.conflicted
                                ? "pill-warn"
                                : f.missing
                                  ? "pill-gray"
                                  : "pill-ok"
                            }`}
                          >
                            {f.conflicted
                              ? "冲突"
                              : f.missing
                                ? "缺失"
                                : "已抽取"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pager
              key={`field-${taskId}`}
              total={allRows.length}
              label="个字段"
              page={fieldSafe}
              totalPages={fieldTotalPages}
              onPrev={() => setFieldPage(fieldSafe - 1)}
              onNext={() => setFieldPage(fieldSafe + 1)}
            />
            {/* 三值语义防误读(spec §4.3;原型 s3 tbl-foot 句式) */}
            <div className="tbl-foot">
              缺失字段按 <code className="k">on_missing_input: need_human</code>{" "}
              处理——不阻断审查,也不计为通过;冲突字段需在基准确认页人工裁定后生效
            </div>
          </>
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
