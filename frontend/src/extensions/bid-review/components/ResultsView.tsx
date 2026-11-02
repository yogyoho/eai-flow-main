"use client";

/**
 * 审查结果专屏(原型 s5;spec §4.5,Plan7 自 WorkbenchView 拆分;裁定8
 * 「审查工作台」退役,路由 /bid-review/results)。
 * EAI-CUSTOM (2026-10-30): 按 docs/designs/2026-10-30-bid-review-ui.html 原型重整,
 * 页面按原型三段在同一路由内分区呈现——s3(步骤条 .stepper + 审查材料小表)、
 * s5(可提交判定横幅 .verdict-band + 风险分布 + 问题清单 .iss 四行卡)、
 * s6(复核交互内联:维持 / 误报四因 .fp-inline / 改严重度 .modal);样式全量走
 * app/bid-review/bid-review.css 的 .brx 类词汇,弃原 SplitPane/Tailwind 拼装。
 * 2026-10-30 二轮 s5 对齐:问题卡头部三 pill(严重度→verdict 码→规则类型码,
 * 灰 pill 显引擎原词 violation/det/engine)+ 规则名作 iss-title + iss-bd 四行
 * (判定结论 iss-verdict→证据→建议+操作→fp-inline)+ need_human 组置底,
 * 组前 .iss-note 分隔线;清单筛选 5 段(无 info 段);风险分布「主要」补
 * violation 提示词,复核进度补「待人工」计数;左列补「规则执行」卡(规则包
 * type 分组判定进度+命中覆盖 meter;后端无逐规则执行遥测,need_human=未完成,
 * 静默跳过不区分,口径见表尾注)。
 * 数据面契约不变:GET /tasks/{id}、GET /tasks/{id}/issues、POST /issues/{id}/feedback
 * (useBidFeedback)。可提交判定=致命未处理>0 一律红「不建议提交」,否则绿「建议提交」;
 * 致命未处理=summary.fatal(引擎口径:排除 need_human)−已判误报的 fatal 条目
 * (误报经后端 apply_false_positive 落库 verdict=false_positive,重取后自然回落);
 * summary 由条目客户端复算(与 worker.summarize_issues 同口径)——api.listTaskIssues
 * 只透出 items,summary 字段在前端契约层不可达。待人工项以 .note-bar 注记
 * 「未判定 ≠ 通过」,不计入可提交判定。
 * 2026-10-30 三轮证据行:det 规则 issue 证据为空时回退展示规则包 inputs 判定输入
 * 字段(routers /rulepacks 回传 inputs);同日证据管线落地(spec
 * 2026-10-30-bid-review-evidence-pipeline-design):抽取 provenance → run_det_rule 后
 * attach_evidence 回填真证据 {doc_id,page,section_path,quote} —— 证据行升格为可点
 * 「定位原文」chip(pdf 真页码直取页;docx 无页码走 quote ±10 段窗口,D8 诚实降级),
 * 404「未定位到原文」如实呈现(DocLocateModal);操作行新增「待人工」
 * (feedback action=need_human,不计违规、confirm 清旗标闭环;已是待人工项隐藏)。
 * 复核状态持久化口径:误报落库(verdict=false_positive,刷新不丢);
 * confirm/severity_change 仅本地 recorded 映射呈现,刷新即失(v1 已记缺口)。
 * 误报原因后端无独立字段,折进 note(「误报原因：<原因>」)。
 * 报告导出(Task 21)行为原样保留:仅 done 可导出,GET report?format=md →
 * Blob→createObjectURL 下载 .md(tests/unit/extensions/bid-review-workbench-export.
 * dom.test.tsx 锁定)。
 */

import { AlertTriangle, BarChart3, Layers } from "lucide-react";
import Link from "next/link";
import {
  type CSSProperties,
  Fragment,
  useEffect,
  useMemo,
  type ReactNode,
  useState,
} from "react";
import { toast } from "sonner";

import { ClipboardSafeStreamdown } from "@/components/ai-elements/streamdown";
import {
  type BidChecklistItem,
  type FeedbackAction,
  type LocateTarget,
  exportReport,
} from "@/extensions/bid-review/api";
import { DocLocateModal } from "@/extensions/bid-review/components/DocLocateModal";
import { formatDuration } from "@/extensions/bid-review/components/primitives";
import { TaskStepper } from "@/extensions/bid-review/components/TaskStepper";
import { TaskTitleTag } from "@/extensions/bid-review/components/TaskTitleTag";
import {
  useBidAttachmentChecklist,
  useBidDiff,
  useBidFeedback,
  useBidIssues,
  useBidRulepacks,
  useBidScoreCoverage,
  useBidTask,
} from "@/extensions/bid-review/hooks";
import { type IssueOut } from "@/extensions/bid-review/types";
import { cn } from "@/lib/utils";

// 定位原文 modal 已抽共享(EAI-CUSTOM 2026-10-30 分期建议一期:BaselineView 字段卡同用)

// ── 筛选/误因/严重度词汇 ────────────────────────────────────────────────
// 2026-10-30 与原型对齐:s5 清单筛选 5 段(全部/致命/主要/次要/待人工);
// info 级问题仍在「全部」与搜索可达,不设独立段。
// Plan9(2026-10-31)导出:s6 复核工作台 seg 筛选同词汇复用。
export type SevFilter = "all" | "fatal" | "major" | "minor" | "human";

export const SEG_OPTIONS: { value: SevFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "fatal", label: "致命" },
  { value: "major", label: "主要" },
  { value: "minor", label: "次要" },
  { value: "human", label: "待人工" },
];

// ── 字段中文名(2026-10-30 用户反馈:引擎 message 里的字段路径是英文)────────
// 与 backend/app/extensions/bid_review/engine/extract.py FIELD_DICTIONARY 同源
// (三方契约:规则包 inputs / 字段字典 / 评测 schema);新字段两处同步。
const FIELD_LABELS: Record<string, string> = {
  "bid.total_price": "投标总价",
  "tender.max_price": "招标最高限价",
  "bid.price_includes_tax": "投标报价含税口径",
  "tender.price_includes_tax": "招标报价含税口径",
  "bid.detail_rows": "投标报价明细行",
  "bid.subtotal": "投标明细合计",
  "bid.total_price_words": "投标总价大写金额",
  "tender.boq_items": "招标工程量清单",
  "bid.boq_items": "投标工程量清单",
  "tender.project_identity.name": "招标项目名称",
  "tender.project_identity.code": "招标项目编号",
  "bid.header_footer.project_name": "投标文件页眉/页脚项目名",
  "bid.entity.license_name": "营业执照投标人名称",
  "bid.entity.name_in_bid_letter": "投标函投标人名称",
  "project.entity_whitelist.names": "项目主体白名单",
  "bid.duration_main_text": "投标正文工期",
  "bid.duration_schedule": "投标进度计划工期",
  "bid.duration_commitment_letter": "投标承诺函工期",
  "bid.amount_occurrences": "投标报价金额(全文出现处)",
  "tender.max_duration": "招标要求工期",
  "bid.warranty_period": "投标质保期",
  "tender.min_warranty_period": "招标最低质保期",
};

/** on_missing_input 处置→中文(引擎词汇;未知值回退原样)。 */
const ON_MISSING_LABELS: Record<string, string> = {
  need_human: "按需人工处理",
  skip: "跳过该项",
  fail: "判为不通过",
};

/**
 * 缺失字段类 message 的中文渲染(2026-10-30 用户反馈):引擎生成
 * 「字段缺失无法判定:a, b(on_missing_input=need_human)」,字段路径是英文——
 * 按 FIELD_LABELS 换中文名、路径以小字码注保留(可对照基准),处置词翻中文;
 * 未命中该模式的消息原样返回(其他规则 message 本就是中文)。原始全文由
 * 调用方放 title 悬浮。export(2026-10-31 二期):复核工作台同用。
 */
const MISSING_FIELDS_RE =
  /^(.+?)[:：]\s*(.+?)\s*\(on_missing_input=([a-z_]+)\)$/;

export function renderIssueMessage(message: string): ReactNode {
  const m = MISSING_FIELDS_RE.exec(message);
  if (!m?.[1] || !m[2] || !m[3]) return message;
  const prefix = m[1];
  const fields = m[2]
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const onMissing = ON_MISSING_LABELS[m[3]] ?? `on_missing_input=${m[3]}`;
  return (
    <>
      {prefix}——缺失字段:
      {fields.map((f, idx) => (
        <span key={f}>
          {idx > 0 ? "、" : ""}
          <span style={{ whiteSpace: "nowrap" }}>
            {FIELD_LABELS[f] ?? "未登记字段"}
            <code className="k" style={{ fontSize: 11, margin: "0 1px" }}>
              {f}
            </code>
          </span>
        </span>
      ))}
      ({onMissing})
    </>
  );
}

/** 误报四因(原型 s5 .fp-inline;必选,后端无独立 reason 字段→折进 note)。
 * export(2026-10-31 二期):复核工作台(ReviewQueueView)同用。 */
export const FP_REASONS = [
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

/** export(2026-10-31 二期):复核工作台(ReviewQueueView)严重度 pill 同用。 */
export function sevPillBrx(severity: string): { cls: string; label: string } {
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
      return {
        cls: "pill-gray",
        label: status === "created" ? "已创建" : status,
      };
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

/** 核对状态 → pill(MATCHED ok / PARTIAL warn / MISSING err / UNKNOWN gray=需人工;L2 P1 spec 2026-11-02 §5 + L2 P2)。 */
function checklistPill(status: string): { label: string; cls: string } {
  switch (status) {
    case "MATCHED":
      return { label: "已提供", cls: "pill pill-ok" };
    case "PARTIAL":
      return { label: "份数不足", cls: "pill pill-warn" };
    case "UNKNOWN":
      return { label: "需人工", cls: "pill pill-gray" };
    default:
      return { label: "缺失", cls: "pill pill-err" };
  }
}

export function ResultsView({ taskId }: { taskId?: string | null }) {
  // 复核状态本地映射:confirm/severity 后端不落 issue 行(v1 缺口),刷新即失;
  // 误报经 apply_false_positive 落库 verdict=false_positive,重取后由服务端数据呈现。
  const [reviewed, setReviewed] = useState<Record<string, FeedbackAction>>({});
  // 报告导出(Task 21):GET report?format=md → Blob 下载;仅 done 可导出。
  const [exporting, setExporting] = useState(false);
  // 报告预览 modal(Plan7 T4,原型 s5):导出改开弹层——免责注记+判定摘要+
  // md 正文;「下载 .md」走既有 handleExportReport。PDF 导出挂账(原型不抄)。
  const [reportOpen, setReportOpen] = useState(false);
  const [reportMd, setReportMd] = useState<string | null>(null);
  useEffect(() => {
    if (!reportOpen || !taskId) return;
    let alive = true;
    setReportMd(null);
    exportReport(taskId)
      .then((b) => b.text())
      .then((t) => {
        if (alive) setReportMd(t);
      })
      .catch((e: unknown) => {
        if (alive) toast.error(e instanceof Error ? e.message : "报告生成失败");
      });
    return () => {
      alive = false;
    };
  }, [reportOpen, taskId]);
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
  // EAI-CUSTOM 2026-10-30:定位原文弹层(证据 chip 点击触发,spec D6/D8)
  const [locate, setLocate] = useState<LocateTarget | null>(null);
  // B7 版本对比卡(spec §4.5):prev_task_id 有值才出按钮;点开才拉 diff(懒加载)
  const [diffOpen, setDiffOpen] = useState(false);

  const enabled = Boolean(taskId);
  const taskQuery = useBidTask(enabled ? taskId : null);
  const issuesQuery = useBidIssues(enabled ? taskId : null);
  const task = taskQuery.data ?? null;
  const diffQuery = useBidDiff(
    diffOpen ? taskId : null,
    diffOpen ? (taskQuery.data?.prev_task_id ?? null) : null,
  );
  // B4 评分覆盖度(spec §5/§4.5):旧任务 total=0 → 回落「规则命中」meter 现状口径
  const coverageQuery = useBidScoreCoverage(enabled ? taskId : null);
  const coverage = coverageQuery.data ?? null;
  // L2 P1 附件核对表(spec 2026-11-02 §4/§5):零投影 → 诚实空态卡
  const checklistQuery = useBidAttachmentChecklist(enabled ? taskId : null);
  const checklist = checklistQuery.data ?? null;
  const clItems = useMemo(() => {
    // rank 显式按 status 联合类型收窄(联合类型扩员时 tsc 编译期报错,而非静默 NaN):
    // UNKNOWN 次于 MISSING(分组失败,待人工)
    const rank: Record<BidChecklistItem["status"], number> = {
      MISSING: 0,
      UNKNOWN: 1,
      PARTIAL: 2,
      MATCHED: 3,
    };
    return [...(checklist?.items ?? [])].sort(
      (a, b) => rank[a.status] - rank[b.status],
    );
  }, [checklist]);
  const feedback = useBidFeedback();
  // 规则名/类型映射(2026-10-30 用户反馈+原型对齐)——GET /rulepacks 联表:
  // 名称作问题卡标题,类型(det/engine)作灰 pill(原型 s5 头部三 pill 结构)。
  const rulepacksQuery = useBidRulepacks();
  const ruleMeta = useMemo(() => {
    const names: Record<string, string> = {};
    const types: Record<string, string> = {};
    const inputs: Record<string, string[]> = {};
    for (const p of rulepacksQuery.data ?? []) {
      for (const r of p.rules) {
        names[r.id] = r.name;
        types[r.id] = r.type;
        inputs[r.id] = r.inputs ?? [];
      }
    }
    return { names, types, inputs };
  }, [rulepacksQuery.data]);

  // 稳定空数组身份(useMemo 依赖 issues 的派生计算不随加载态每帧重算)
  // L2 P2 跨层去重:grouped 行(已被更强同实体问题归并)由展示层隐藏,
  // summary 随之只计可见——与后端全量 summary 并存,口径注见 tbl-foot。
  const issues = useMemo(
    () => (issuesQuery.data ?? []).filter((i) => !i.grouped_into),
    [issuesQuery.data],
  );
  // "基准未确认"唯一可靠信号:deep 任务停在确认门(worker 落 awaiting_confirm)。
  const baselineUnconfirmed = task?.status === "awaiting_confirm";
  // 计划 Task 17 Step 2:确认前 workbench 只读。
  const readOnly = baselineUnconfirmed;

  // 步骤条输入已收敛进共享件 TaskStepper(Plan6)

  // 审查材料:engine_meta.docs({doc_id,role:tender|bid})
  const rawDocs = task?.engine_meta?.docs;
  const docs = (Array.isArray(rawDocs) ? rawDocs : []).filter(isRecord);

  // 误报判定:服务端落库 verdict 优先,本地 recorded 兜底(重取落定前的瞬态一致)。
  // 服务端 review_state(B2,spec §4.5)→ 动作语义反向映射;会话内动作优先覆盖,
  // 刷新后 refetch 落定——进度计数与行级标签刷新不丢(旧实现维持数仅本地会话内)。
  const stateAction = (s?: string): FeedbackAction | undefined =>
    s === "maintained"
      ? "confirm"
      : s === "false_positive"
        ? "false_positive"
        : s === "severity_changed"
          ? "severity_change"
          : s === "deferred"
            ? "need_human"
            : undefined;
  const actionOf = (i: IssueOut): FeedbackAction | undefined =>
    reviewed[i.id] ?? stateAction(i.review_state);

  const isFp = (i: IssueOut) =>
    actionOf(i) === "false_positive" || i.verdict === "false_positive";

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

  // 复核进度(§4.5 B2:服务端 review_state + 会话内覆盖;误报含旧 verdict 兜底)
  const fpCount = issues.filter(isFp).length;
  const confirmCount = issues.filter((i) => actionOf(i) === "confirm").length;
  const reviewedTotal = issues.filter((i) => actionOf(i) != null).length;

  // 规则执行(2026-10-30 原型 s5 左列补齐):按规则包 type 分组——deterministic
  // 一组,semantic/hybrid 并入语义组(与 worker 进度文案「det+sem/hyb」同口径)。
  // 每任务无逐规则执行遥测,诚实口径:need_human 规则=「未完成」,其余无法区分
  // 「执行无发现」与「静默跳过」,按已完成计——表尾注记口径,勿当执行日志读。
  const allPackRules = useMemo(
    () => (rulepacksQuery.data ?? []).flatMap((p) => p.rules),
    [rulepacksQuery.data],
  );
  const ruleExec = useMemo(() => {
    const detTotal = allPackRules.filter(
      (r) => r.type === "deterministic",
    ).length;
    const semTotal = allPackRules.length - detTotal;
    const humanRules = new Set(
      issues.filter((i) => i.need_human).map((i) => i.rule_id),
    );
    let detHuman = 0;
    let semHuman = 0;
    for (const id of humanRules) {
      if (ruleMeta.types[id] === "deterministic") detHuman += 1;
      else semHuman += 1;
    }
    return {
      detTotal,
      semTotal,
      detDone: detTotal - detHuman,
      semDone: semTotal - semHuman,
      detHuman,
      semHuman,
      hitRules: new Set(issues.map((i) => i.rule_id)).size,
      total: allPackRules.length,
    };
  }, [allPackRules, issues, ruleMeta.types]);

  // 裁定 16(2026-10-31 用户):原「资料完备性」卡删除——缺失字段已在 /parsing
  // 基准字段抽取卡(含值/锚点)呈现,受影响规则已在问题清单「待确认」组逐条可见,
  // 本卡为同一事实的第三次重复且无操作入口。

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

  // 原型 s5 顺序:普通问题在前,need_human 组置底,组前 .iss-note 分隔线。
  const ordered = [
    ...filtered.filter((i) => !i.need_human),
    ...filtered.filter((i) => i.need_human),
  ];

  // 客户端分页(2026-10-30 用户要求;后端 issues 无分页参数):每页 10 条,
  // 筛选/搜索变化回第 1 页;越界页码收敛(issues 重取后变少不空白)。
  const PAGE_SIZE = 10;
  const [page, setPage] = useState(1);
  useEffect(() => {
    setPage(1);
  }, [seg, q]);
  const totalPages = Math.max(1, Math.ceil(ordered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageItems = ordered.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

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
          if (action === "need_human") toast.success("已标记待人工");
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
        <div
          className="card"
          style={{ padding: "56px 24px", textAlign: "center" }}
        >
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
            审查结果
            <TaskTitleTag taskId={taskId} bizNo={task?.biz_no} />
          </h2>
          <div className="ph-sub">
            {task
              ? `合规红线与一致性审查结论,逐条问题含证据定位与复核入口 · ${task.mode === "deep" ? "深度评审" : "快速审查"}${task.done_at ? ` · 用时 ${formatDuration(task.created_at, task.done_at)}` : ""}`
              : "任务详情加载中…"}
          </div>
        </div>
        <div className="ph-actions">
          {/* B7 版本对比(spec §4.5):有上一版本才出;点开行内卡片(懒拉 diff) */}
          {task?.prev_task_id ? (
            <button
              type="button"
              className="btn btn-sec btn-sm"
              onClick={() => setDiffOpen((v) => !v)}
            >
              对比上一版本
            </button>
          ) : null}
          {/* B10 版本链(spec 2026-11-01 §2.3):换版重审=以本任务为基准发起新审查,
              跳任务总览深链自动开对话框并预选基准 */}
          <Link
            href={`/bid-review?prev=${taskId}`}
            className="btn btn-sec btn-sm"
            title="以本任务为对比基准,上传新版投标文件发起新审查"
          >
            换版重审
          </Link>
          {/* 常驻(原型 s5):发起复核——出结果才可用,未完成置灰注因 */}
          {taskId ? (
            <Link
              href={`/bid-review/review?task_id=${taskId}`}
              className="btn btn-sec btn-sm"
              aria-disabled={task?.status !== "done" || undefined}
              title={
                task && task.status !== "done"
                  ? "审查完成后可发起复核"
                  : "到复核工作台逐条处置待人工问题"
              }
              style={
                task && task.status !== "done"
                  ? { opacity: 0.5, pointerEvents: "none" }
                  : undefined
              }
            >
              发起复核
            </Link>
          ) : null}
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => {
              void taskQuery.refetch();
              void issuesQuery.refetch();
              toast.success("已刷新");
            }}
          >
            刷新
          </button>
          {baselineUnconfirmed ? (
            <span className="pill pill-orange">
              <span className="dot dot-warn" />
              待基准确认
            </span>
          ) : null}
          {st ? <span className={cn("pill", st.cls)}>{st.label}</span> : null}
          {/* 常驻基准确认入口(二期 spec §六):不随状态消失——确认后仍可回看
              基线/冲突裁定;待确认时升主色 */}
          <Link
            href={`/bid-review/baseline?task_id=${taskId}`}
            className={cn(
              "btn btn-sm",
              baselineUnconfirmed ? "btn-pri" : "btn-sec",
            )}
          >
            基准确认
          </Link>
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
            onClick={() => setReportOpen(true)}
          >
            导出报告
          </button>
        </div>
      </div>

      {/* 步骤条:共享件(Plan6 上移,canonical home=/parsing;M3 拆分前暂留) */}
      <TaskStepper task={task} />

      {/* B7 版本对比卡(spec §4.5,轻量不做 s8 整屏):三态计数+新增问题列表;
          匹配键=规则+锚定字段(dedup_key),消失问题详情在上一版任务 */}
      {diffOpen && task?.prev_task_id ? (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-hd">
            <h3>版本对比</h3>
            <span className="hd-sub">
              与上一版本逐问题对照(匹配键 = 规则 + 锚定字段)
            </span>
            <div className="hd-right">
              {/* B10 (spec §2.2):整屏入口——行内卡只做三态速览,字段级差异看 /diff */}
              <Link
                href={`/bid-review/diff?task_id=${taskId}&prev=${task.prev_task_id}`}
                className="btn btn-txt btn-sm"
              >
                查看整屏
              </Link>
              <span className="pill pill-warn">
                新增 {diffQuery.data?.added.length ?? "—"}
              </span>
              <span className="pill pill-gray">
                消失 {diffQuery.data?.removed.length ?? "—"}
              </span>
              <span className="pill pill-ok">
                未变 {diffQuery.data?.unchanged_count ?? "—"}
              </span>
            </div>
          </div>
          {diffQuery.isPending ? (
            <div className="tbl-foot">对比加载中…</div>
          ) : diffQuery.isError ? (
            <div className="tbl-foot">
              对比加载失败:{diffQuery.error.message}
            </div>
          ) : (
            <>
              {(diffQuery.data?.added.length ?? 0) === 0 ? (
                <div className="tbl-foot">本版本无新增问题</div>
              ) : (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>规则</th>
                      <th>严重度</th>
                      <th>问题</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diffQuery.data!.added.map((a) => {
                      const sp = sevPillBrx(a.severity);
                      return (
                        <tr key={a.id}>
                          <td className="mono">{a.rule_id}</td>
                          <td>
                            <span className={cn("pill", sp.cls)}>
                              {sp.label}
                            </span>
                          </td>
                          <td>{renderIssueMessage(a.message)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <div className="tbl-foot">
                按「规则 + 锚定字段」匹配三态;消失问题详情见上一版本任务
              </div>
            </>
          )}
        </div>
      ) : null}

      {/* 基准未确认:确认门注记(确认前工作台只读);确认后状态离开即移除 */}
      {baselineUnconfirmed ? (
        <div
          className="note-bar warnbar"
          style={{ marginTop: 0, marginBottom: 12 }}
        >
          <AlertTriangle className="ic" />
          <span style={{ flex: 1 }}>
            基准未确认——基准错误将批量产生错误结论;确认前工作台只读。
          </span>
          <Link href={`/bid-review/baseline?task_id=${taskId}`}>
            前往基准确认
          </Link>
        </div>
      ) : null}

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
        <div
          className="note-bar errbar"
          style={{ marginTop: 0, marginBottom: 12 }}
        >
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
            <div
              className="gate1-metrics"
              style={{ gridTemplateColumns: "1fr 1fr" }}
            >
              <div className="gate1-m">
                <span className={cn("v", fatalUnhandled > 0 ? "bad" : "zero")}>
                  {fatalUnhandled}
                </span>
                <span className="l">致命</span>
                <span className="h">violation</span>
              </div>
              <div className="gate1-m">
                <span className="v hot">{summary.major}</span>
                <span className="l">主要</span>
                <span className="h">violation</span>
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
              <span style={{ flex: 1 }}>
                待人工为引擎无法判定项——<b>未判定 ≠ 通过</b>
                ,不计入可提交判定,整改与复核时必须逐条处理。
              </span>
              {/* 二期 spec §五:复核工作台(s6 队列视图)入口 */}
              <Link href={`/bid-review/review?task_id=${taskId}`}>
                到复核工作台
              </Link>
            </div>
          ) : null}

          {/* 裁定 16:资料完备性卡已删(重复信息,见 useMemo 处注记) */}

          {/* 规则执行(原型 s5 左列):规则包 type 分组判定进度 + 命中覆盖 */}
          {allPackRules.length > 0 ? (
            <div className="card" style={{ marginBottom: 12 }}>
              <div className="card-hd">
                <h3>规则执行</h3>
                <span className="hd-sub">
                  判定进度 · 规则包 {allPackRules.length} 条
                </span>
              </div>
              <table className="tbl">
                <tbody>
                  <tr>
                    <td>确定性规则</td>
                    <td className="r num">
                      {ruleExec.detDone} / {ruleExec.detTotal}
                    </td>
                    <td className="r">
                      {ruleExec.detHuman > 0 ? (
                        <span className="pill pill-warn">
                          待人工 {ruleExec.detHuman}
                        </span>
                      ) : (
                        <span className="pill pill-ok">全部判定</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td>语义(sem/hyb)</td>
                    <td className="r num">
                      {ruleExec.semDone} / {ruleExec.semTotal}
                    </td>
                    <td className="r">
                      {ruleExec.semHuman > 0 ? (
                        <span className="pill pill-warn">
                          待人工 {ruleExec.semHuman}
                        </span>
                      ) : (
                        <span className="pill pill-ok">全部判定</span>
                      )}
                    </td>
                  </tr>
                  {(coverage?.total ?? 0) > 0 && coverage ? (
                    <tr>
                      <td>评分覆盖度</td>
                      <td className="r">
                        <span className="meter">
                          <i
                            style={{
                              width: `${Math.round((coverage.covered / coverage.total) * 100)}%`,
                            }}
                          />
                        </span>
                        <span className="num">
                          {Math.round(
                            (coverage.covered / coverage.total) * 100,
                          )}
                          %
                        </span>
                      </td>
                      <td className="r" style={{ color: "var(--text-3)" }}>
                        评分办法 {coverage.total} 项已覆盖 {coverage.covered}
                      </td>
                    </tr>
                  ) : (
                    <tr>
                      <td>规则命中</td>
                      <td className="r">
                        <span className="meter">
                          <i
                            style={{
                              width: `${ruleExec.total ? Math.round((ruleExec.hitRules / ruleExec.total) * 100) : 0}%`,
                            }}
                          />
                        </span>
                        <span className="num">
                          {ruleExec.total
                            ? Math.round(
                                (ruleExec.hitRules / ruleExec.total) * 100,
                              )
                            : 0}
                          %
                        </span>
                      </td>
                      <td className="r" style={{ color: "var(--text-3)" }}>
                        命中 {ruleExec.hitRules} / {ruleExec.total} 条
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="tbl-foot">
                口径:待人工计未完成;静默跳过(on_missing_input=skip)不区分
                {(coverage?.total ?? 0) > 0
                  ? ";评分覆盖度 = 评分办法项相关字段与启用规则判定输入的交集,未覆盖不代表审错——规则包未设该维度规则"
                  : ""}
              </div>
            </div>
          ) : null}

          {/* ── L2 P1 附件核对表卡(spec 2026-11-02 §5;L2 P2 增需人工格):六格 counts + 明细(pill 映射/
              页码 chip 复用 DocLocate role=bid 首文档)/EXTRA info 灰行不进问题数 ── */}
          {checklist && checklist.counts.required > 0 ? (
            <div className="card">
              <div className="card-hd">
                <h3>附件核对表</h3>
                <span className="hd-sub">
                  招标要求 {checklist.counts.required} 项 ·
                  两级精确匹配(编号/名称)
                </span>
              </div>
              <div className="metric-strip">
                <div className="metric-cell">
                  <div className="m-lb">要求附件</div>
                  <div className="m-v">{checklist.counts.required}</div>
                </div>
                <div className="metric-cell">
                  <div className="m-lb">已提供</div>
                  <div className="m-v">{checklist.counts.matched}</div>
                </div>
                <div className="metric-cell warn">
                  <div className="m-lb">份数不足</div>
                  <div className="m-v">{checklist.counts.partial}</div>
                </div>
                <div className="metric-cell err">
                  <div className="m-lb">缺失</div>
                  <div className="m-v">{checklist.counts.missing}</div>
                </div>
                <div className="metric-cell">
                  <div className="m-lb">需人工</div>
                  <div className="m-v">{checklist.counts.unknown ?? 0}</div>
                </div>
                <div className="metric-cell">
                  <div className="m-lb">多余附件</div>
                  <div className="m-v">{checklist.counts.extra}</div>
                </div>
              </div>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>要求附件</th>
                    <th>强制</th>
                    <th>份数</th>
                    <th>提供情况</th>
                    <th>页码</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {clItems
                    .filter((it) => it.status !== "MATCHED" || it.found > 0)
                    .map((it, i) => {
                      const pill = checklistPill(it.status);
                      const first = it.refs[0];
                      return (
                        <tr key={`${it.no}-${it.name}-${i}`}>
                          <td className="num">{i + 1}</td>
                          <td>
                            {it.no ? (
                              <span className="mono">{it.no} </span>
                            ) : null}
                            {it.name}
                            {(it.sub_results?.length ?? 0) > 0 ? (
                              <div className="hd-sub">
                                子件:
                                {(it.sub_results ?? [])
                                  .map(
                                    (s) =>
                                      `${s.no ? `${s.no} ` : ""}${s.name} ${s.found > 0 ? "✓" : "✗"}`,
                                  )
                                  .join(" · ")}
                              </div>
                            ) : null}
                            {it.clause ? (
                              <span className="hd-sub">（{it.clause}）</span>
                            ) : null}
                          </td>
                          <td>
                            {it.mandatory === "★" || it.mandatory === "必需"
                              ? "必需"
                              : it.mandatory || "—"}
                          </td>
                          <td>
                            {it.min_count
                              ? `${it.found}/${it.min_count}`
                              : it.found}
                          </td>
                          <td>
                            {it.status === "UNKNOWN"
                              ? "无法自动分组"
                              : it.found > 0
                                ? `已提供 ${it.found} 份`
                                : "未提供"}
                          </td>
                          <td>
                            {first && first.doc_id && taskId ? (
                              <button
                                type="button"
                                className="src-chip"
                                onClick={() =>
                                  setLocate({
                                    docId: first.doc_id as string,
                                    page: first.page,
                                    quote: "",
                                  })
                                }
                              >
                                {first.doc_id}
                                {first.page != null ? ` p.${first.page}` : ""}
                              </button>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            <span className={pill.cls}>{pill.label}</span>
                          </td>
                        </tr>
                      );
                    })}
                  {checklist.extra_items.map((ex, i) => (
                    <tr key={`extra-${i}`} className="unmapped-row">
                      <td className="num">+</td>
                      <td className="unmapped-cell">{ex.name}</td>
                      <td>—</td>
                      <td>—</td>
                      <td>招标要求外</td>
                      <td>
                        {ex.doc_id && taskId ? (
                          <button
                            type="button"
                            className="src-chip"
                            onClick={() =>
                              setLocate({
                                docId: ex.doc_id as string,
                                page: ex.page,
                                quote: "",
                              })
                            }
                          >
                            {ex.doc_id}
                            {ex.page != null ? ` p.${ex.page}` : ""}
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        <span className="pill pill-gray">多余</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="tbl-foot">
                口径：EXTRA 多余附件仅提示不判错不进问题数；MATCHED
                全提供项默认收起，缺失/份数不足优先展示（L2-020/L2-024
                规则组）。
              </div>
            </div>
          ) : checklist && checklist.counts.required === 0 ? (
            <div className="card">
              <div className="tbl-foot">
                本任务抽取时未包含附件要求维度——重新抽取后即可生成附件核对表（旧任务无此数据，不回填）。
              </div>
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
              <span style={{ color: "var(--text-3)" }}>
                待人工 <b className="num">{summary.need_human}</b>
              </span>
            </div>
            <div className="tbl-foot">
              误报项不进报告正文,自动回流评测集;跨层归并(grouped)行不重复展示——前端计数为可见行口径,后端
              summary 为全量口径(L2 P2)
            </div>
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
              <div
                style={{ display: "flex", flexDirection: "column", gap: 10 }}
              >
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
              pageItems.map((i, idx) => {
                const absIdx = (safePage - 1) * PAGE_SIZE + idx;
                const sp = sevPillBrx(i.severity);
                // need_human(含服务端 deferred)不算复核完成(待人工项须可继续
                // 确认/误报 闭环——后端 confirm 会清 need_human 旗标)
                const reviewedAction = actionOf(i);
                const doneState =
                  (reviewedAction != null && reviewedAction !== "need_human") ||
                  i.verdict === "false_positive";
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
                // det 规则 issue 证据为空(rule_runner 硬编码 evidence:[];A-* 锚点注册表 anchors.py 未落地,
                // 抽取层也无逐字段 doc/page 溯源)——回退展示规则包 inputs 判定输入字段,真数据不造假
                const evFields =
                  evList.length === 0 ? (ruleMeta.inputs[i.rule_id] ?? []) : [];
                // need_human 组首项前插分隔线(按全量 ordered 绝对下标判定,跨页不丢)
                const showHumanDivider =
                  i.need_human &&
                  !(absIdx > 0 && ordered[absIdx - 1]?.need_human);
                return (
                  <Fragment key={i.id}>
                    {showHumanDivider ? (
                      <div className="iss-note">
                        以下为引擎无法判定项(need_human)——未判定 ≠
                        通过,不计入可提交判定,复核时逐条处理:
                      </div>
                    ) : null}
                    <div
                      className={cn("iss", doneState && "done")}
                      data-sev={i.need_human ? "human" : i.severity}
                    >
                      <div className="iss-hd">
                        <span className="dot" style={sevDotStyle(i)} />
                        <span className="iss-rule">{i.rule_id}</span>
                        {/* 原型 s5 头部 pill:严重度(待人工=warn)→ verdict 码 → 规则类型码,灰 pill 显引擎原词 */}
                        {i.need_human ? (
                          <span className="pill pill-warn">待人工</span>
                        ) : (
                          <span className={cn("pill", sp.cls)}>{sp.label}</span>
                        )}
                        <span
                          className="pill pill-gray"
                          style={{ height: 18, fontSize: 11 }}
                        >
                          {i.verdict}
                        </span>
                        {ruleMeta.types[i.rule_id] ? (
                          <span
                            className="pill pill-gray"
                            style={{ height: 18, fontSize: 11 }}
                          >
                            {ruleMeta.types[i.rule_id]}
                          </span>
                        ) : null}
                        {/* 原型 iss-title=规则名;悬浮 title 保留引擎原始全文 */}
                        <span className="iss-title" title={i.message}>
                          {ruleMeta.names[i.rule_id] ?? i.message}
                        </span>
                        <span className="iss-ckw">
                          {doneState ? (
                            <span
                              className={cn(
                                "pill",
                                isFp(i) ? "pill-gray" : "pill-ok",
                              )}
                              style={{ height: 18, fontSize: 11 }}
                            >
                              {isFp(i)
                                ? "已复核 · 误报"
                                : reviewedAction === "severity_change"
                                  ? "已复核 · 严重度调整"
                                  : "已复核 · 维持违规"}
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
                        {/* 原型四行:判定结论(中文字段渲染,悬浮原始全文)→ 证据 → 建议+操作 → fp-inline */}
                        <div className="iss-verdict" title={i.message}>
                          {renderIssueMessage(i.message)}
                        </div>
                        {/* L2 P2 跨层去重:本行已并入更强同实体问题,关联原行折叠在此 */}
                        {(i.related_issues?.length ?? 0) > 0 ? (
                          <div className="hd-sub">
                            关联问题 {i.related_issues!.length}:
                            {i
                              .related_issues!.map(
                                (r) =>
                                  `[${r.rule_id} ${r.severity}] ${r.message}`,
                              )
                              .join(";")}
                          </div>
                        ) : null}
                        {evList.length > 0 ||
                        evFields.length > 0 ||
                        i.clause_id ||
                        i.confidence < 1 ? (
                          <div className="iss-ev">
                            <span>证据:</span>
                            {evList.length === 0 && evFields.length > 0 ? (
                              <span style={{ color: "var(--text-3)" }}>
                                确定性规则,依据字段:
                              </span>
                            ) : null}
                            {evFields.map((f) => (
                              <code
                                key={f}
                                className="k"
                                title={`判定输入字段 ${f}(取值见上方结论行)`}
                              >
                                {f}
                              </code>
                            ))}
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
                                {/* EAI-CUSTOM 2026-10-30:真证据 chip 可点 → 定位原文弹层
                                  (pdf 带真页码直取页;docx 无页码走 quote 片段窗口) */}
                                <button
                                  type="button"
                                  className="src-chip src-chip-btn"
                                  title={
                                    ev.text ? `定位原文:${ev.text}` : "定位原文"
                                  }
                                  onClick={() =>
                                    setLocate({
                                      docId: ev.docId,
                                      page:
                                        typeof ev.page === "number"
                                          ? ev.page
                                          : null,
                                      quote: ev.text,
                                    })
                                  }
                                >
                                  {ev.docId}
                                  {ev.page != null ? <b>p.{ev.page}</b> : null}
                                </button>
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
                            {i.clause_id ? (
                              <code className="k">{i.clause_id}</code>
                            ) : null}
                            {i.confidence < 1 ? (
                              <span
                                className="num"
                                style={{ color: "var(--text-3)" }}
                              >
                                置信度 {Math.round(i.confidence * 100)}%
                              </span>
                            ) : null}
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
                                disabled={readOnly || feedback.isPending}
                                onClick={() => submitFeedback(i, "confirm")}
                              >
                                {i.need_human ? "确认问题" : "维持违规"}
                              </button>
                              <button
                                type="button"
                                className="btn btn-sec btn-sm"
                                disabled={readOnly || feedback.isPending}
                                onClick={() => {
                                  setFpReason("");
                                  setFpOpenId(fpOpenId === i.id ? null : i.id);
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
                              {/* EAI-CUSTOM 2026-10-30(spec D9):待人工动作——引擎无法
                                判定的人工挂起,不计违规;已是待人工项隐藏本按钮 */}
                              {!i.need_human ? (
                                <button
                                  type="button"
                                  className="btn btn-sec btn-sm"
                                  disabled={readOnly || feedback.isPending}
                                  onClick={() =>
                                    submitFeedback(i, "need_human")
                                  }
                                >
                                  待人工
                                </button>
                              ) : null}
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
                  </Fragment>
                );
              })
            )}
            <div className="tbl-foot">
              <span>
                共 {issues.length} 项问题
                {seg !== "all" || needle
                  ? ` · 当前显示 ${filtered.length} 项`
                  : ""}
              </span>
              {totalPages > 1 ? (
                <>
                  <span style={{ flex: 1 }} />
                  <button
                    type="button"
                    className="btn btn-sec btn-sm"
                    disabled={safePage <= 1}
                    onClick={() => setPage(safePage - 1)}
                  >
                    上一页
                  </button>
                  <span className="num">
                    第 {safePage} / {totalPages} 页
                  </span>
                  <button
                    type="button"
                    className="btn btn-sec btn-sm"
                    disabled={safePage >= totalPages}
                    onClick={() => setPage(safePage + 1)}
                  >
                    下一页
                  </button>
                </>
              ) : null}
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
        <div
          className="overlay open"
          role="dialog"
          aria-modal="true"
          aria-label="调整严重度"
        >
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
                onClick={() =>
                  submitFeedback(sevTarget, "severity_change", "", sevValue)
                }
              >
                {feedback.isPending ? "提交中…" : "提交"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 定位原文 modal(EAI-CUSTOM 2026-10-30:证据 chip → 溯源取数端点) */}
      {locate && taskId ? (
        <DocLocateModal
          taskId={taskId}
          target={locate}
          onClose={() => setLocate(null)}
        />
      ) : null}

      {/* 批量误报 modal(四因必选;原因折进 note) */}
      {batchFpOpen ? (
        <div
          className="overlay open"
          role="dialog"
          aria-modal="true"
          aria-label="批量标记误报"
        >
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

      {/* 报告预览 modal(Plan7 T4,原型 s5 L1327):免责注记+判定摘要(复用
          verdict 计算)+ md 正文(Streamdown);「下载 .md」走既有下载逻辑 */}
      {reportOpen ? (
        <div
          className="overlay open"
          role="dialog"
          aria-modal="true"
          aria-label="审查报告预览"
        >
          <div className="modal" style={{ maxWidth: 860, width: "92%" }}>
            <div className="modal-hd">
              <h3>审查报告预览</h3>
              <button
                type="button"
                className="x"
                aria-label="关闭"
                onClick={() => setReportOpen(false)}
              >
                ✕
              </button>
            </div>
            <div className="modal-bd">
              <div
                className="note-bar warnbar"
                style={{ marginTop: 0, marginBottom: 12 }}
              >
                <AlertTriangle className="ic" />
                <span>本报告为辅助提示,最终责任由投标主体承担。</span>
              </div>
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
                    判定口径:存在 severity=fatal 且未被人工判误报的问题(致命
                    &gt; 0 一律红)
                  </span>
                </div>
              ) : null}
              <div style={{ marginTop: 12 }}>
                {reportMd === null ? (
                  <span style={{ color: "var(--text-3)" }}>报告生成中…</span>
                ) : (
                  <ClipboardSafeStreamdown>{reportMd}</ClipboardSafeStreamdown>
                )}
              </div>
            </div>
            <div className="modal-ft">
              <button
                type="button"
                className="btn btn-sec"
                onClick={() => setReportOpen(false)}
              >
                关闭
              </button>
              <button
                type="button"
                className="btn btn-pri"
                disabled={exporting || task?.status !== "done"}
                title={
                  task && task.status !== "done"
                    ? "审查完成后可导出报告"
                    : "导出审查报告(.md)"
                }
                onClick={() => void handleExportReport()}
              >
                {exporting ? "导出中…" : "下载 .md"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
