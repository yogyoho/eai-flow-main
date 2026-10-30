"use client";

/**
 * 审查工作台(bid:page:workbench)——Task 17,核心视图。
 * EAI-CUSTOM (2026-10-30): 按 docs/designs/2026-10-30-bid-review-ui.html 原型重整,
 * 页面按原型三段在同一路由内分区呈现——s3(步骤条 .stepper + 审查材料小表)、
 * s5(可提交判定横幅 .verdict-band + 风险分布 + 问题清单 .iss 四行卡)、
 * s6(复核交互内联:维持 / 误报四因 .fp-inline / 改严重度 .modal);样式全量走
 * app/bid-review/bid-review.css 的 .brx 类词汇,弃原 SplitPane/Tailwind 拼装。
 * 数据面契约不变:GET /tasks/{id}、GET /tasks/{id}/issues、POST /issues/{id}/feedback
 * (useBidFeedback)。可提交判定=致命未处理>0 一律红「不建议提交」,否则绿「建议提交」;
 * 致命未处理=summary.fatal(引擎口径:排除 need_human)−已判误报的 fatal 条目
 * (误报经后端 apply_false_positive 落库 verdict=false_positive,重取后自然回落);
 * summary 由条目客户端复算(与 worker.summarize_issues 同口径)——api.listTaskIssues
 * 只透出 items,summary 字段在前端契约层不可达。待人工项以 .note-bar 注记
 * 「未判定 ≠ 通过」,不计入可提交判定。
 * 复核状态持久化口径:误报落库(verdict=false_positive,刷新不丢);
 * confirm/severity_change 仅本地 recorded 映射呈现,刷新即失(v1 已记缺口)。
 * 误报原因后端无独立字段,折进 note(「误报原因：<原因>」)。
 * 报告导出(Task 21)行为原样保留:仅 done 可导出,GET report?format=md →
 * Blob→createObjectURL 下载 .md(tests/unit/extensions/bid-review-workbench-export.
 * dom.test.tsx 锁定)。
 */

import { AlertTriangle, BarChart3, Layers } from "lucide-react";
import Link from "next/link";
import { type CSSProperties, useEffect, useState } from "react";
import { toast } from "sonner";

import { type FeedbackAction, exportReport } from "@/extensions/bid-review/api";
import {
  useBidFeedback,
  useBidIssues,
  useBidTask,
} from "@/extensions/bid-review/hooks";
import { type IssueOut } from "@/extensions/bid-review/types";
import { cn } from "@/lib/utils";

// ── 步骤条(原型 s3:6 步;stage 词汇=worker progress.stage)──────────────
const STAGE_LABELS = [
  "已创建",
  "文档解析",
  "字段抽取",
  "基准确认",
  "审查执行",
  "完成",
] as const;

const STAGE_INDEX: Record<string, number> = {
  created: 0,
  parsing: 1,
  extracting: 2,
  confirm_gate: 3,
  review: 4,
  done: 5,
};

/** 当前步:progress.stage 优先;缺失时按任务状态兜底(测试夹具/早期任务无 stage)。 */
function resolveStageIdx(stageRaw: string | null, status: string): number {
  if (stageRaw && stageRaw in STAGE_INDEX) return STAGE_INDEX[stageRaw]!;
  switch (status) {
    case "done":
    case "completed":
      return 5;
    case "running":
      return 4;
    case "awaiting_confirm":
      return 3;
    case "extracting":
      return 2;
    case "parsing":
      return 1;
    default:
      return 0;
  }
}

// ── 筛选/误因/严重度词汇 ────────────────────────────────────────────────
type SevFilter = "all" | "fatal" | "major" | "minor" | "info" | "human";

const SEG_OPTIONS: { value: SevFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "fatal", label: "致命" },
  { value: "major", label: "主要" },
  { value: "minor", label: "次要" },
  { value: "info", label: "提示" },
  { value: "human", label: "待人工" },
];

/** 误报四因(原型 s5 .fp-inline;必选,后端无独立 reason 字段→折进 note)。 */
const FP_REASONS = [
  "规则误判",
  "证据错位",
  "口径理解不同",
  "基准抽取错误",
] as const;

const SEVERITIES = [
  { value: "fatal", label: "致命" },
  { value: "major", label: "主要" },
  { value: "minor", label: "次要" },
  { value: "info", label: "提示" },
] as const;

// ── .brx pill 词汇映射(原型 s5)────────────────────────────────────────

function sevPillBrx(severity: string): { cls: string; label: string } {
  switch (severity) {
    case "fatal":
      return { cls: "pill-err", label: "致命" };
    case "major":
      return { cls: "pill-orange", label: "主要" };
    case "minor":
      return { cls: "pill-gray", label: "次要" };
    case "info":
      return { cls: "pill-gray", label: "提示" };
    default:
      return { cls: "pill-gray", label: severity || "未知" };
  }
}

function verdictPillBrx(verdict: string): { cls: string; label: string } {
  switch (verdict) {
    case "false_positive":
      return { cls: "pill-ok", label: "误报" };
    case "pass":
      return { cls: "pill-ok", label: "通过" };
    case "need_human":
      return { cls: "pill-gray", label: "待人工" };
    default:
      return { cls: "pill-gray", label: verdict === "violation" ? "违规" : verdict || "未知" };
  }
}

function taskStatusPillBrx(status: string): { cls: string; label: string } {
  switch (status) {
    case "done":
    case "completed":
      return { cls: "pill-ok", label: "已完成" };
    case "failed":
      return { cls: "pill-err", label: "失败" };
    case "running":
      return { cls: "pill-main", label: "进行中" };
    case "parsing":
      return { cls: "pill-main", label: "解析中" };
    case "extracting":
      return { cls: "pill-main", label: "基准提取中" };
    case "awaiting_confirm":
      return { cls: "pill-warn", label: "待确认" };
    default:
      return { cls: "pill-gray", label: status === "created" ? "已创建" : status };
  }
}

/** 严重度→头部圆点(原型 s5:fatal 红 / major 橙 / 次要灰 / 待人工虚线.warn)。 */
function sevDotStyle(issue: IssueOut): CSSProperties {
  if (issue.need_human)
    return {
      border: "2px dashed var(--warn-700)",
      width: 8,
      height: 8,
      background: "transparent",
    };
  if (issue.severity === "fatal") return { background: "var(--error-500)" };
  if (issue.severity === "major") return { background: "var(--second-500)" };
  return { background: "var(--gray-400)" };
}

// ── 工具 ────────────────────────────────────────────────────────────────

const isRecord = (x: unknown): x is Record<string, unknown> =>
  typeof x === "object" && x !== null;

/** evidence 条目字段安全取串(no-base-to-string):非串值 JSON 化,缺省回退。 */
function str(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (v == null) return fallback;
  return JSON.stringify(v);
}

/** 日期段用连字符 yyyy-MM-dd(TasksView 同款;zh-CN toLocaleString 是斜杠)。 */
function formatDate(s: string): string {
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function WorkbenchView({ taskId }: { taskId?: string | null }) {
  // 复核状态本地映射:confirm/severity 后端不落 issue 行(v1 缺口),刷新即失;
  // 误报经 apply_false_positive 落库 verdict=false_positive,重取后由服务端数据呈现。
  const [reviewed, setReviewed] = useState<Record<string, FeedbackAction>>({});
  // 报告导出(Task 21):GET report?format=md → Blob 下载;仅 done 可导出。
  const [exporting, setExporting] = useState(false);
  // 清单筛选/搜索(客户端)
  const [seg, setSeg] = useState<SevFilter>("all");
  const [q, setQ] = useState("");
  // 批量勾选
  const [checked, setChecked] = useState<Set<string>>(new Set());
  // 单条误报:inline 四因
  const [fpOpenId, setFpOpenId] = useState<string | null>(null);
  const [fpReason, setFpReason] = useState("");
  // 改严重度 modal
  const [sevTarget, setSevTarget] = useState<IssueOut | null>(null);
  const [sevValue, setSevValue] = useState("major");
  // 批量误报 modal(四因必选)
  const [batchFpOpen, setBatchFpOpen] = useState(false);
  const [batchReason, setBatchReason] = useState("");

  const enabled = Boolean(taskId);
  const taskQuery = useBidTask(enabled ? taskId : null);
  const issuesQuery = useBidIssues(enabled ? taskId : null);
  const feedback = useBidFeedback();

  const task = taskQuery.data ?? null;
  const issues = issuesQuery.data ?? [];
  // "基准未确认"唯一可靠信号:deep 任务停在确认门(worker 落 awaiting_confirm)。
  const baselineUnconfirmed = task?.status === "awaiting_confirm";
  // 计划 Task 17 Step 2:确认前 workbench 只读。
  const readOnly = baselineUnconfirmed;

  // 步骤条输入:task.progress {stage,pct,msg}
  const progress: Record<string, unknown> = task?.progress ?? {};
  const stageRaw = typeof progress.stage === "string" ? progress.stage : null;
  const pctVal = typeof progress.pct === "number" ? progress.pct : null;
  const progressMsg = typeof progress.msg === "string" ? progress.msg : "";
  const stageIdx = resolveStageIdx(stageRaw, task?.status ?? "");
  const taskDone = task?.status === "done";

  // 审查材料:engine_meta.docs({doc_id,role:tender|bid})
  const rawDocs = task?.engine_meta?.docs;
  const docs = (Array.isArray(rawDocs) ? rawDocs : []).filter(isRecord);

  // 误报判定:服务端落库 verdict 优先,本地 recorded 兜底(重取落定前的瞬态一致)。
  const isFp = (i: IssueOut) =>
    i.verdict === "false_positive" || reviewed[i.id] === "false_positive";

  // 汇总分级(与 worker.summarize_issues 同口径:severity 各级排除 need_human,
  // 待人工单列;api 层不透出 summary,客户端复算)。
  const summary = { fatal: 0, major: 0, minor: 0, info: 0, need_human: 0 };
  for (const i of issues) {
    if (i.need_human) summary.need_human += 1;
    else if (i.severity === "fatal") summary.fatal += 1;
    else if (i.severity === "major") summary.major += 1;
    else if (i.severity === "minor") summary.minor += 1;
    else summary.info += 1;
  }
  // 致命未处理 = summary.fatal − 已判误报的 fatal 条目(误报落库后自然回落)。
  const fatalFp = issues.filter(
    (i) => i.severity === "fatal" && !i.need_human && isFp(i),
  ).length;
  const fatalUnhandled = summary.fatal - fatalFp;

  // 复核进度(误报=服务端+本地并集;维持仅本地会话内)
  const fpCount = issues.filter(isFp).length;
  const confirmCount = issues.filter((i) => reviewed[i.id] === "confirm").length;
  const reviewedTotal = fpCount + confirmCount;

  // 客户端过滤:seg(致命/主要/次要/提示排除待人工条目,与 summary 口径一致)+ 搜索 q
  const needle = q.trim().toLowerCase();
  const filtered = issues.filter((i) => {
    const segOk =
      seg === "all"
        ? true
        : seg === "human"
          ? i.need_human
          : i.severity === seg && !i.need_human;
    if (!segOk) return false;
    if (!needle) return true;
    return [i.rule_id, i.message, i.fix, i.clause_id ?? ""].some((s) =>
      s.toLowerCase().includes(needle),
    );
  });

  const segCount = (v: SevFilter): number =>
    v === "all"
      ? issues.length
      : v === "human"
        ? summary.need_human
        : summary[v];

  // 报告导出(Task 21):仅 done 可导;Blob→createObjectURL 下载 .md(测试锁定)。
  const handleExportReport = async () => {
    if (!taskId) return;
    setExporting(true);
    try {
      const blob = await exportReport(taskId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bid-review-report-${taskId.slice(0, 8)}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "报告导出失败");
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    if (feedback.isError) {
      toast.error(feedback.error?.message ?? "复核提交失败");
    }
  }, [feedback.isError, feedback.error]);

  // 单条复核:mutate + onSuccess 本地映射 + toast(照既有逻辑)
  const submitFeedback = (
    issue: IssueOut,
    action: FeedbackAction,
    note = "",
    newSeverity?: string,
  ) => {
    if (!taskId) return;
    feedback.mutate(
      {
        issueId: issue.id,
        taskId,
        action,
        note,
        ...(action === "severity_change" && newSeverity
          ? { new_severity: newSeverity }
          : {}),
      },
      {
        onSuccess: () => {
          setReviewed((prev) => ({ ...prev, [issue.id]: action }));
          if (action === "confirm") toast.success("已确认该问题");
          if (action === "false_positive") {
            toast.success("已标记误报");
            setFpOpenId(null);
            setFpReason("");
          }
          if (action === "severity_change") {
            const label =
              SEVERITIES.find((s) => s.value === newSeverity)?.label ??
              newSeverity ??
              "";
            toast.success(`严重度已调整为${label}`);
            setSevTarget(null);
          }
        },
      },
    );
  };

  // 批量维持:逐条 confirm(mutateAsync 顺序提交;错误靠 feedback.isError toast)
  const batchConfirm = async () => {
    if (!taskId) return;
    let ok = 0;
    for (const id of checked) {
      try {
        await feedback.mutateAsync({
          issueId: id,
          taskId,
          action: "confirm",
          note: "",
        });
        setReviewed((prev) => ({ ...prev, [id]: "confirm" }));
        ok += 1;
      } catch {
        break;
      }
    }
    if (ok > 0) toast.success(`已批量维持 ${ok} 项`);
    setChecked(new Set());
  };

  // 批量误报:四因必选,原因折进 note(后端无独立 reason 字段)
  const batchFalsePositive = async () => {
    if (!taskId || !batchReason) return;
    let ok = 0;
    for (const id of checked) {
      try {
        await feedback.mutateAsync({
          issueId: id,
          taskId,
          action: "false_positive",
          note: `误报原因：${batchReason}`,
        });
        setReviewed((prev) => ({ ...prev, [id]: "false_positive" }));
        ok += 1;
      } catch {
        break;
      }
    }
    if (ok > 0) toast.success(`已批量标记误报 ${ok} 项`);
    setChecked(new Set());
    setBatchFpOpen(false);
    setBatchReason("");
  };

  const toggleChecked = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (!taskId) {
    return (
      <div className="screen on">
        <div className="card" style={{ padding: "56px 24px", textAlign: "center" }}>
          <p style={{ color: "var(--text-3)", marginBottom: 12 }}>
            未指定任务——请从任务列表进入工作台
          </p>
          <Link href="/bid-review" className="btn btn-sec">
            返回任务列表
          </Link>
        </div>
      </div>
    );
  }

  const st = task ? taskStatusPillBrx(task.status) : null;

  return (
    <div className="screen on">
      {/* ═══ 区段一(原型 s3):页头 + 步骤条 + 审查材料 ═══ */}
      <div className="page-head">
        <div className="ph-icon">
          <Layers className="ic" />
        </div>
        <div>
          <h2>
            审查工作台 · <span className="mono">{taskId.slice(0, 8)}</span>
          </h2>
          <div className="ph-sub">
            {task
              ? `${task.mode === "deep" ? "深度评审" : "快速审查"} · 创建于 ${formatDate(task.created_at)}`
              : "任务详情加载中…"}
          </div>
        </div>
        <div className="ph-actions">
          {baselineUnconfirmed ? (
            <span className="pill pill-orange">
              <span className="dot dot-warn" />
              待基准确认
            </span>
          ) : null}
          {st ? <span className={cn("pill", st.cls)}>{st.label}</span> : null}
          {/* 报告导出(Task 21):仅 done 可导,行为契约测试锁定 */}
          <button
            type="button"
            className="btn btn-pri btn-sm"
            disabled={exporting || task?.status !== "done"}
            title={
              task && task.status !== "done"
                ? "审查完成后可导出报告"
                : "导出审查报告(.md)"
            }
            onClick={() => void handleExportReport()}
          >
            {exporting ? "导出中…" : "导出报告"}
          </button>
        </div>
      </div>

      {/* 步骤条:task.progress {stage,pct,msg} → done/on */}
      <div className="stepper">
        {STAGE_LABELS.map((label, i) => (
          <span
            key={label}
            className={cn(
              "step",
              (taskDone || i < stageIdx) && "done",
              !taskDone && i === stageIdx && "on",
            )}
          >
            <span className="sn">{i + 1}</span>
            {label}
          </span>
        ))}
      </div>
      {progressMsg ? (
        <div className="tbl-foot">
          引擎:{progressMsg}
          {pctVal != null ? (
            <span className="num"> · {pctVal}%</span>
          ) : null}
        </div>
      ) : null}

      {/* 基准未确认:确认门注记(确认前工作台只读);确认后状态离开即移除 */}
      {baselineUnconfirmed ? (
        <div className="note-bar warnbar" style={{ marginTop: 0, marginBottom: 12 }}>
          <AlertTriangle className="ic" />
          <span style={{ flex: 1 }}>
            基准未确认——基准错误将批量产生错误结论;确认前工作台只读。
          </span>
          <Link href={`/bid-review/baseline?task_id=${taskId}`}>前往基准确认</Link>
        </div>
      ) : null}

      {/* 审查失败:引擎错误原样注记 */}
      {task?.status === "failed" ? (
        <div className="note-bar errbar" style={{ marginTop: 0, marginBottom: 12 }}>
          <AlertTriangle className="ic" />
          <span>审查失败:{task.error ?? "未知错误"}</span>
        </div>
      ) : null}

      {/* 审查材料小表:engine_meta.docs {doc_id, role} */}
      {docs.length > 0 ? (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-hd">
            <h3>审查材料</h3>
            <span className="hd-sub">{docs.length} 个文件</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>文档</th>
                  <th>角色</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d, idx) => {
                  const role = str(d.role);
                  return (
                    <tr key={idx}>
                      <td className="mono">{str(d.doc_id, "未知文档")}</td>
                      <td>
                        <span
                          className={
                            role === "tender"
                              ? "pill pill-main"
                              : role === "bid"
                                ? "pill pill-orange"
                                : "pill pill-gray"
                          }
                        >
                          {role === "tender"
                            ? "招标"
                            : role === "bid"
                              ? "投标"
                              : role || "未知"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {/* ═══ 区段二(原型 s5):可提交判定横幅 + 风险分布 + 问题清单 ═══ */}
      {issues.length > 0 ? (
        <div
          className={cn("verdict-band", fatalUnhandled === 0 && "ok")}
          role="status"
        >
          <span className="vb-ic">
            <AlertTriangle className="ic" />
          </span>
          <div>
            <h3>{fatalUnhandled > 0 ? "不建议提交" : "建议提交"}</h3>
            <div className="vb-sub">
              {fatalUnhandled > 0
                ? `命中致命红线 ${fatalUnhandled} 项,建议整改后重新审查`
                : "无未处理致命问题——次要与待人工项仍须逐条处理后提交"}
            </div>
          </div>
          <span className="vb-cjk">
            判定口径:存在 severity=fatal 且未被人工判误报的问题(致命 &gt; 0
            一律红)
          </span>
        </div>
      ) : null}

      {issuesQuery.isError ? (
        <div className="note-bar errbar" style={{ marginTop: 0, marginBottom: 12 }}>
          <AlertTriangle className="ic" />
          <span style={{ flex: 1 }}>
            问题列表加载失败:{issuesQuery.error.message}
          </span>
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void issuesQuery.refetch()}
          >
            重试
          </button>
        </div>
      ) : null}

      <div className="split">
        {/* 左:风险分布 + 待人工注记 + 复核进度(原型 s5 左列) */}
        <div>
          <div className="gate1-card">
            <div className="gate1-hd">
              <span className="gate1-badge">
                <BarChart3 className="ic" />
              </span>
              <div>
                <h3>风险分布</h3>
                <div className="hd-sub">
                  {issues.length} 项问题 · 已复核 {reviewedTotal}
                </div>
              </div>
            </div>
            <div className="gate1-metrics" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="gate1-m">
                <span className={cn("v", fatalUnhandled > 0 ? "bad" : "zero")}>
                  {fatalUnhandled}
                </span>
                <span className="l">致命未处理</span>
                <span className="h">violation</span>
              </div>
              <div className="gate1-m">
                <span className="v hot">{summary.major}</span>
                <span className="l">主要</span>
              </div>
              <div className="gate1-m">
                <span className="v">{summary.minor}</span>
                <span className="l">次要</span>
              </div>
              <div className="gate1-m">
                <span className="v" style={{ color: "var(--warn-700)" }}>
                  {summary.need_human}
                </span>
                <span className="l">待人工</span>
                <span className="h">need_human</span>
              </div>
            </div>
          </div>

          {summary.need_human > 0 ? (
            <div className="note-bar warnbar" style={{ margin: "0 0 12px" }}>
              <AlertTriangle className="ic" />
              <span>
                待人工为引擎无法判定项——<b>未判定 ≠ 通过</b>
                ,不计入可提交判定,整改与复核时必须逐条处理。
              </span>
            </div>
          ) : null}

          <div className="card">
            <div className="card-hd">
              <h3>复核进度</h3>
            </div>
            <div
              style={{
                padding: "12px 16px",
                fontSize: 13,
                display: "flex",
                gap: 14,
                flexWrap: "wrap",
              }}
            >
              <span>
                已复核 <b className="num">{reviewedTotal}</b> / {issues.length}
              </span>
              <span style={{ color: "var(--text-3)" }}>
                维持 <b className="num">{confirmCount}</b>
              </span>
              <span style={{ color: "var(--text-3)" }}>
                误报 <b className="num">{fpCount}</b>
              </span>
            </div>
            <div className="tbl-foot">误报项不进报告正文,自动回流评测集</div>
          </div>
        </div>

        {/* 右:问题清单(.seg 筛选 + 搜索 + .iss 四行卡 + .batch-bar) */}
        <div className="card">
          <div className="toolbar">
            <div className="seg" role="group" aria-label="严重度筛选">
              {SEG_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={cn(seg === opt.value && "on")}
                  aria-pressed={seg === opt.value}
                  onClick={() => setSeg(opt.value)}
                >
                  {opt.label} <span className="num">{segCount(opt.value)}</span>
                </button>
              ))}
            </div>
            <input
              className="inp"
              placeholder="搜索规则 / 关键词…"
              style={{ width: 170 }}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <div style={{ padding: "12px 14px 14px" }}>
            {issuesQuery.isPending ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="animate-pulse"
                    style={{
                      height: 56,
                      borderRadius: 8,
                      background: "var(--gray-100)",
                    }}
                  />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <p
                style={{
                  color: "var(--text-3)",
                  textAlign: "center",
                  padding: "32px 0",
                  fontSize: 13,
                }}
              >
                {issues.length === 0 ? "暂无问题记录" : "当前过滤条件下无问题"}
              </p>
            ) : (
              filtered.map((i) => {
                const sp = sevPillBrx(i.severity);
                const vp = verdictPillBrx(isFp(i) ? "false_positive" : i.verdict);
                const reviewedAction = reviewed[i.id];
                const doneState =
                  reviewedAction != null || i.verdict === "false_positive";
                const evList = i.evidence.filter(isRecord).map((ev) => ({
                  docId: str(ev.doc_id, "未知文档"),
                  page:
                    typeof ev.page === "number"
                      ? ev.page
                      : typeof ev.page === "string" && ev.page
                        ? ev.page
                        : null,
                  sectionPath: str(ev.section_path),
                  text: str(ev.text),
                }));
                return (
                  <div
                    key={i.id}
                    className={cn("iss", doneState && "done")}
                    data-sev={i.need_human ? "human" : i.severity}
                  >
                    <div className="iss-hd">
                      <span className="dot" style={sevDotStyle(i)} />
                      <span className="iss-rule">{i.rule_id}</span>
                      {i.need_human ? (
                        <span className="pill pill-warn">待人工</span>
                      ) : (
                        <span className={cn("pill", sp.cls)}>{sp.label}</span>
                      )}
                      <span
                        className={cn("pill", vp.cls)}
                        style={{ height: 18, fontSize: 11 }}
                      >
                        {vp.label}
                      </span>
                      <span className="iss-title">{i.message}</span>
                      <span className="iss-ckw">
                        {doneState ? (
                          <span
                            className={cn(
                              "pill",
                              isFp(i) ? "pill-gray" : "pill-ok",
                            )}
                            style={{ height: 18, fontSize: 11 }}
                          >
                            {isFp(i) ? "已复核 · 误报" : "已复核 · 维持"}
                          </span>
                        ) : (
                          <label className="iss-ckw">
                            <input
                              type="checkbox"
                              className="iss-ck"
                              aria-label="选中该问题"
                              checked={checked.has(i.id)}
                              disabled={readOnly}
                              onChange={() => toggleChecked(i.id)}
                            />
                          </label>
                        )}
                      </span>
                    </div>
                    <div className="iss-bd">
                      {i.need_human ? (
                        <div className="iss-note">
                          引擎无法判定项——未判定 ≠ 通过,须人工核对后再处理。
                        </div>
                      ) : null}
                      {i.clause_id || i.confidence < 1 ? (
                        <div className="iss-ev" style={{ color: "var(--text-3)" }}>
                          <span>结论补充:</span>
                          {i.clause_id ? <code className="k">{i.clause_id}</code> : null}
                          {i.confidence < 1 ? (
                            <span className="num">
                              置信度 {Math.round(i.confidence * 100)}%
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                      {evList.length > 0 ? (
                        <div className="iss-ev">
                          <span>证据:</span>
                          {evList.map((ev, idx) => (
                            <span
                              key={idx}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 6,
                                minWidth: 0,
                              }}
                            >
                              <span className="src-chip" title={ev.text}>
                                {ev.docId}
                                {ev.page != null ? <b>p.{ev.page}</b> : null}
                              </span>
                              {ev.sectionPath ? (
                                <code className="k">{ev.sectionPath}</code>
                              ) : null}
                              {ev.text ? (
                                <span
                                  className="truncate"
                                  style={{
                                    maxWidth: 320,
                                    color: "var(--text-3)",
                                  }}
                                  title={ev.text}
                                >
                                  {ev.text}
                                </span>
                              ) : null}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      <div className="iss-ft">
                        {i.fix ? (
                          <span className="iss-fix">
                            <b>建议</b> {i.fix}
                          </span>
                        ) : (
                          <span className="iss-fix" />
                        )}
                        {!doneState ? (
                          <span className="iss-acts">
                            <button
                              type="button"
                              className="btn btn-sec btn-sm"
                              disabled={
                                readOnly ||
                                reviewedAction === "confirm" ||
                                feedback.isPending
                              }
                              onClick={() => submitFeedback(i, "confirm")}
                            >
                              维持
                            </button>
                            <button
                              type="button"
                              className="btn btn-sec btn-sm"
                              disabled={readOnly || feedback.isPending}
                              onClick={() => {
                                setFpReason("");
                                setFpOpenId(
                                  fpOpenId === i.id ? null : i.id,
                                );
                              }}
                            >
                              误报
                            </button>
                            <button
                              type="button"
                              className="btn btn-sec btn-sm"
                              disabled={readOnly || feedback.isPending}
                              onClick={() => {
                                setSevValue(i.severity);
                                setSevTarget(i);
                              }}
                            >
                              改严重度
                            </button>
                            {readOnly ? (
                              <span
                                style={{
                                  fontSize: 12,
                                  color: "var(--text-3)",
                                }}
                              >
                                基准确认前工作台只读
                              </span>
                            ) : null}
                          </span>
                        ) : null}
                      </div>
                      {fpOpenId === i.id && !doneState ? (
                        <div className="fp-inline">
                          <span className="fp-t">
                            标记误报需选择原因(将回流评测集):
                          </span>
                          {FP_REASONS.map((r) => (
                            <label key={r}>
                              <input
                                type="radio"
                                name={`fp-${i.id}`}
                                checked={fpReason === r}
                                onChange={() => setFpReason(r)}
                              />
                              {r}
                            </label>
                          ))}
                          <button
                            type="button"
                            className="btn btn-pri btn-sm"
                            style={{ marginLeft: 8 }}
                            disabled={!fpReason || feedback.isPending}
                            onClick={() =>
                              submitFeedback(
                                i,
                                "false_positive",
                                `误报原因：${fpReason}`,
                              )
                            }
                          >
                            提交误报
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })
            )}
            <div className="tbl-foot">
              共 {issues.length} 项问题
              {seg !== "all" || needle ? ` · 当前显示 ${filtered.length} 项` : ""}
            </div>
            {checked.size > 0 ? (
              <div className="batch-bar">
                <span>
                  已选 <b className="num">{checked.size}</b> 项
                </span>
                <span style={{ flex: 1 }} />
                <button
                  type="button"
                  className="btn bb-sec btn-sm"
                  disabled={readOnly || feedback.isPending}
                  onClick={() => void batchConfirm()}
                >
                  批量维持
                </button>
                <button
                  type="button"
                  className="btn btn-pri btn-sm"
                  disabled={readOnly || feedback.isPending}
                  onClick={() => {
                    setBatchReason("");
                    setBatchFpOpen(true);
                  }}
                >
                  批量标误报
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* ═══ 区段三(原型 s6):复核判定浮层 ═══ */}
      {/* 改严重度 modal(action=severity_change + new_severity) */}
      {sevTarget ? (
        <div className="overlay open" role="dialog" aria-modal="true" aria-label="调整严重度">
          <div className="modal">
            <div className="modal-hd">
              <h3>调整严重度</h3>
              <button
                type="button"
                className="x"
                aria-label="关闭"
                onClick={() => setSevTarget(null)}
              >
                ✕
              </button>
            </div>
            <div className="modal-bd">
              <div className="frm-row">
                <label>
                  对问题 <span className="mono">{sevTarget.rule_id}</span>{" "}
                  重新定级;提交后回流复核记录。
                </label>
                <select
                  className="inp"
                  value={sevValue}
                  onChange={(e) => setSevValue(e.target.value)}
                >
                  {SEVERITIES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="modal-ft">
              <button
                type="button"
                className="btn btn-sec"
                onClick={() => setSevTarget(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn-pri"
                disabled={feedback.isPending}
                onClick={() => submitFeedback(sevTarget, "severity_change", "", sevValue)}
              >
                {feedback.isPending ? "提交中…" : "提交"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 批量误报 modal(四因必选;原因折进 note) */}
      {batchFpOpen ? (
        <div className="overlay open" role="dialog" aria-modal="true" aria-label="批量标记误报">
          <div className="modal">
            <div className="modal-hd">
              <h3>批量标记误报</h3>
              <button
                type="button"
                className="x"
                aria-label="关闭"
                onClick={() => setBatchFpOpen(false)}
              >
                ✕
              </button>
            </div>
            <div className="modal-bd">
              <div className="frm-row">
                <label>
                  将对 <b className="num">{checked.size}</b>{" "}
                  项问题提交误报——原因必选(回流评测集):
                </label>
                <div className="radio-line">
                  {FP_REASONS.map((r) => (
                    <label key={r}>
                      <input
                        type="radio"
                        name="batch-fp-reason"
                        checked={batchReason === r}
                        onChange={() => setBatchReason(r)}
                      />
                      {r}
                    </label>
                  ))}
                </div>
              </div>
              {!batchReason ? (
                <div className="note-bar" style={{ marginTop: 0 }}>
                  <AlertTriangle className="ic" />
                  <span>
                    请选择误报原因后提交——无原因的误报无法归因,评测集不接受
                  </span>
                </div>
              ) : null}
            </div>
            <div className="modal-ft">
              <button
                type="button"
                className="btn btn-sec"
                onClick={() => setBatchFpOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn-pri"
                disabled={!batchReason || feedback.isPending}
                onClick={() => void batchFalsePositive()}
              >
                {feedback.isPending ? "提交中…" : "提交误报"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
