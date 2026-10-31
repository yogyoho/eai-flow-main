"use client";

/**
 * EAI-CUSTOM (2026-10-30): 任务工作台参照 docs/designs/2026-10-30-bid-review-ui.html
 * s1(任务列表)/s2(新建审查任务)重整——结构照抄原型,类词汇全取 .brx 作用域
 * (app/bid-review/bid-review.css),数据仍走真实 hooks(GET /tasks 聚合 +
 * POST /tasks multipart)。工具条(搜索+状态 seg)/骨架屏/空态充满为 2026-10-30
 * 用户定案补齐;搜索为客户端过滤——列表端点无分页/过滤参数(TaskOut 亦无项目名
 * 字段,故只搜任务号;服务端过滤待后端补参数后切换)。原型件取舍:导出列表、
 * 规则包/模型选择未迁(v1 无对应后端能力);文案保留 v1 真实口径,不照抄原型虚构
 * 的规则条数/耗时。
 * 计数契约(伪零纪律,tests/unit/extensions/bid-review-tasks-view.dom.test.tsx 锁定):
 * 未经测量 ≠ 零——行级致命未处理/待人工与卡片 Σ 都由 GET /tasks 每任务聚合字段
 * (fatal_unhandled/need_human_count)填实;处理中任务(created/parsing/extracting/
 * running,半程快照)与 null 计数一律「—」;存在未定型任务或统计缺失时卡片 Σ 同样
 * 「—」(部分和也是编造);列表加载失败五卡全「—」。口径(误报剔除/need_human 计入)
 * 由后端 pytest 锁定(test_bid_review_routers.py::test_list_tasks_per_task_issue_counts)。
 * 新建 = .overlay/.modal(原型 s2 三段结构):mode-card 单选 quick/deep + 招标/投标
 * 两组上传(POST /tasks multipart 是后端唯一文档入口,零材料任务会被后端
 * _enqueue_docs 无条件直推空跑,故必传——Task 12 修复轮决定 (b));创建成功跳
 * workbench?task_id=。
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, ListChecks, Plus, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createTask } from "@/extensions/bid-review/api";
import { bidReviewKeys, useBidTasks } from "@/extensions/bid-review/hooks";
import { type TaskOut } from "@/extensions/bid-review/types";
import { cn } from "@/lib/utils";

const HEADERS = ["任务号", "模式", "状态", "致命未处理", "待人工", "创建时间"];

/** 工作台深链(工作台真实地址;旧 /bid-review/tasks/{id} 重定向页仅保旧深链兼容)。 */
function workbenchHref(taskId: string): string {
  return `/bid-review/workbench?task_id=${encodeURIComponent(taskId)}`;
}

const MODE_META: Record<
  "quick" | "deep",
  { label: string; desc: string; hint: string }
> = {
  quick: {
    label: "快速评审",
    desc: "确定性规则快审(M1 子集),上传文件后自动执行,秒级完成。",
    hint: "无需基准确认,任务创建即自动开始审查。",
  },
  deep: {
    label: "深度评审",
    desc: "全量规则深审(含语义逐条审,耗时较长);生成基线后需在工作台人工确认再续跑。",
    hint: "创建后进入「基准确认」卡点,基准未确认前不开始审查。",
  },
};

const MODE_PILL: Record<string, { cls: string; label: string }> = {
  quick: { cls: "pill-gray", label: "快速评审" },
  deep: { cls: "pill-main", label: "深度评审" },
};

/** 模式 pill(原型 s1:quick=pill-gray 快速评审 / deep=pill-main 深度评审)。 */
function modePill(mode: string): { cls: string; label: string } {
  return MODE_PILL[mode] ?? { cls: "pill-gray", label: mode };
}

/**
 * 状态 pill 映射到原型 .pill 词汇(后端 models.py:30:created|parsing|extracting|
 * awaiting_confirm|running|done|failed;终态成功是 done,completed 仅兼容别名):
 * done=pill-ok / failed=pill-err / running,parsing,extracting=pill-main /
 * awaiting_confirm=pill-warn / created=gray;非终态带活性 dot(原型 s1 习语)。
 */
function statusPill(status: string): {
  cls: string;
  dot: string | null;
  label: string;
} {
  switch (status) {
    case "done":
    case "completed":
      return { cls: "pill-ok", dot: null, label: "已完成" };
    case "failed":
      return { cls: "pill-err", dot: null, label: "失败" };
    case "running":
      return { cls: "pill-main", dot: "dot-ok", label: "进行中" };
    case "parsing":
      return { cls: "pill-main", dot: "dot-ok", label: "解析中" };
    case "extracting":
      return { cls: "pill-main", dot: "dot-ok", label: "基准提取中" };
    case "awaiting_confirm":
      return { cls: "pill-warn", dot: "dot-warn", label: "待基准确认" };
    default:
      return {
        cls: "pill-gray",
        dot: null,
        label: status === "created" || status === "pending" ? "已创建" : status,
      };
  }
}

/** 已出问题结果的任务状态——created/parsing/extracting/running 的问题集是半程快照,
 * 计数未定型,行内显示 —(micro-A 2026-10-29:后端计数只对该段状态有意义)。 */
const RESULT_STATUSES = new Set(["done", "awaiting_confirm", "failed"]);

/** 工具条状态 seg(原型 s1 五档:全部/进行中/待确认/已完成/失败;
 * 「进行中」= 未出结果的全部在途态)。客户端过滤,见头部注释的升级路径。 */
const STATUS_FILTERS = [
  { key: "all", label: "全部" },
  { key: "active", label: "进行中" },
  { key: "awaiting_confirm", label: "待基准确认" },
  { key: "done", label: "已完成" },
  { key: "failed", label: "失败" },
] as const;

type StatusFilter = (typeof STATUS_FILTERS)[number]["key"];

function matchStatusFilter(t: TaskOut, f: StatusFilter): boolean {
  switch (f) {
    case "all":
      return true;
    case "active":
      return !RESULT_STATUSES.has(t.status);
    case "awaiting_confirm":
      return t.status === "awaiting_confirm";
    case "done":
      return t.status === "done" || t.status === "completed";
    case "failed":
      return t.status === "failed";
  }
}

/**
 * 行级计数量格(致命未处理/待人工两列共用)。计数=后端 GET /tasks 聚合字段
 * (micro-A 2026-10-29,口径=致命且未被人工判误报 / need_human 旗标,后端 pytest
 * 锁定);处理中任务(半程快照)与计数缺失(null=未统计)显示 ———未经测量不得
 * 显示 0(伪零纪律);>0 致命走 .v-hot 红档(原型 s1 致命/主要列习语)。
 */
function CountCell({
  task,
  field,
}: {
  task: TaskOut;
  field: "fatal_unhandled" | "need_human_count";
}) {
  const gated = !RESULT_STATUSES.has(task.status);
  const count = task[field];
  if (gated || count == null) {
    return (
      <span
        className="unmapped-cell num"
        title={gated ? "任务未出结果,暂无统计" : "问题统计未取到"}
      >
        —
      </span>
    );
  }
  return (
    <span
      className={cn("num", field === "fatal_unhandled" && count > 0 && "v-hot")}
    >
      {count}
    </span>
  );
}

/** 日期段用连字符 yyyy-MM-dd(用户定案 2026-10-16,zh-CN toLocaleString 是斜杠)。 */
function formatDate(s: string): string {
  const d = new Date(s);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

/** s2 上传组:.drop 拖拽/点击上传 + 已选文件表(移除)。input 藏进 label 触发
 * 文件选择;onChange 后清空 value,便于重选同一文件。 */
function FileGroup({
  label,
  files,
  onAdd,
  onRemove,
}: {
  label: string;
  files: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
}) {
  return (
    <div className="frm-row">
      <label>
        {label}
        <span className="must">*</span>
      </label>
      <div
        className="drop"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          onAdd(Array.from(e.dataTransfer.files ?? []));
        }}
      >
        拖拽文件到此处,或
        <label className="btn btn-txt btn-sm" style={{ cursor: "pointer" }}>
          点击上传
          <input
            type="file"
            multiple
            aria-label={`选择${label}`}
            style={{ display: "none" }}
            onChange={(e) => {
              onAdd(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
        </label>
        (可多选;招标与投标文件至少各一份)
      </div>
      {files.length > 0 ? (
        <table className="tbl" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>文件名</th>
              <th className="r">大小</th>
              <th className="r" style={{ paddingRight: 12 }}>
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            {files.map((f, i) => (
              <tr key={`${f.name}-${i}`}>
                <td className="q-ttl" title={f.name}>
                  {f.name}
                </td>
                <td className="r num">{formatSize(f.size)}</td>
                <td className="r">
                  <button
                    type="button"
                    className="btn btn-txt btn-sm"
                    onClick={() => onRemove(i)}
                  >
                    移除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

export function TasksView() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [mode, setMode] = useState<"quick" | "deep">("quick");
  const [tenderFiles, setTenderFiles] = useState<File[]>([]);
  const [bidFiles, setBidFiles] = useState<File[]>([]);

  const tasksQuery = useBidTasks();

  const createMutation = useMutation({
    mutationFn: (input: {
      mode: "quick" | "deep";
      tender: File[];
      bid: File[];
    }) => createTask(input.mode, input),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: bidReviewKeys.tasks });
      setDialogOpen(false);
      router.push(workbenchHref(created.id));
    },
  });

  /** 打开新建 modal:清残留文件与上次错误(创建成功/取消后再开都是干净态)。 */
  const openDialog = () => {
    setTenderFiles([]);
    setBidFiles([]);
    createMutation.reset();
    setDialogOpen(true);
  };

  // Esc 关闭(沿原 Radix Dialog 行为)
  useEffect(() => {
    if (!dialogOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDialogOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dialogOpen]);

  const tasks = tasksQuery.data ?? [];
  // 五格指标:三格状态计数(列表在手即真值,isError 时同样不给数);两格 Σ 走
  // 「全测满才求和」门(micro-A 2026-10-29):全部任务均已出结果(RESULT_STATUSES)
  // 且各自计数已取到,才给数字;存在未定型任务或统计缺失时显示 ———统计未测全时
  // 任何数字(包括部分和、包括 0)都是编造(伪零纪律)。
  const listOk = !tasksQuery.isError;
  const awaitingCount = tasks.filter(
    (t) => t.status === "awaiting_confirm",
  ).length;
  const runningCount = tasks.filter((t) => t.status === "running").length;
  const doneCount = tasks.filter((t) => t.status === "done").length;
  const statTasks = tasks.filter((t) => RESULT_STATUSES.has(t.status));
  const allMeasured =
    !tasksQuery.isError &&
    tasks.length === statTasks.length &&
    statTasks.every(
      (t) => t.fatal_unhandled != null && t.need_human_count != null,
    );
  const fatalCount = allMeasured
    ? statTasks.reduce((sum, t) => sum + (t.fatal_unhandled ?? 0), 0)
    : null;
  const needHumanCount = allMeasured
    ? statTasks.reduce((sum, t) => sum + (t.need_human_count ?? 0), 0)
    : null;

  // 工具条客户端过滤:任务号关键字(忽略大小写)∩ 状态档;列表端点无服务端过滤
  const kw = q.trim().toLowerCase();
  const filtered = tasks.filter(
    (t) =>
      matchStatusFilter(t, statusFilter) &&
      (kw === "" || t.id.toLowerCase().includes(kw)),
  );

  return (
    <div className="screen on brx-fill">
      {/* ── page-head(原型 s1)── */}
      <div className="page-head">
        <div className="ph-icon">
          <ListChecks className="ic" aria-hidden="true" />
        </div>
        <div>
          <h2>任务工作台</h2>
          <div className="ph-sub">投标方案合规红线与一致性审查 · 全部任务</div>
        </div>
        <div className="ph-actions">
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void tasksQuery.refetch()}
            disabled={tasksQuery.isFetching}
          >
            <RefreshCw
              className={cn("ic", tasksQuery.isFetching && "animate-spin")}
              aria-hidden="true"
            />
            刷新
          </button>
          <button
            type="button"
            className="btn btn-pri btn-sm"
            onClick={openDialog}
          >
            <Plus className="ic" aria-hidden="true" />
            新建审查任务
          </button>
        </div>
      </div>

      {/* ── metric-strip 五格骨架(shimmer .sk;refetch 不闪,isPending 才出)── */}
      {tasksQuery.isPending ? (
        <div className="metric-strip" aria-hidden="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="metric-cell">
              <span className="metric-label">
                <span className="sk" style={{ width: 56, height: 12 }} />
              </span>
              <span className="metric-value">
                <span className="sk" style={{ width: 32, height: 20 }} />
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="metric-strip">
          <div className="metric-cell warn">
            <span className="metric-label">
              <span className="dot dot-warn"></span>待基准确认
            </span>
            <span className="metric-value num">
              {listOk ? awaitingCount : "—"}
            </span>
          </div>
          <div className="metric-cell err">
            <span className="metric-label">待人工复核</span>
            <span className="metric-value num">{needHumanCount ?? "—"}</span>
          </div>
          <div className="metric-cell accent">
            <span className="metric-label">运行中</span>
            <span className="metric-value num">
              {listOk ? runningCount : "—"}
            </span>
          </div>
          <div className="metric-cell err">
            <span className="metric-label">致命未处理</span>
            <span className="metric-value num">{fatalCount ?? "—"}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">已完成</span>
            <span className="metric-value num">
              {listOk ? doneCount : "—"}
              <small>个</small>
            </span>
          </div>
        </div>
      )}

      {/* ── 错误态(原型 .note-bar.errbar 词汇 + 重试)── */}
      {tasksQuery.isError ? (
        <div className="note-bar errbar" role="alert">
          <Info className="ic" aria-hidden="true" />
          <span className="flex-1">
            任务列表加载失败:{tasksQuery.error.message}
          </span>
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void tasksQuery.refetch()}
          >
            重试
          </button>
        </div>
      ) : null}

      {/* ── 任务表(原型 s1 .tbl;表头工具条=搜索+状态 seg,客户端过滤)── */}
      {tasksQuery.isPending ? (
        <div className="card">
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  {HEADERS.map((h, i) => (
                    <th
                      key={h}
                      scope="col"
                      className={cn(i >= 3 && i <= 4 && "r")}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody aria-hidden="true">
                {[0, 1, 2, 3, 4, 5].map((row) => (
                  <tr key={row}>
                    <td>
                      <span className="sk" style={{ width: 72, height: 14 }} />
                    </td>
                    <td>
                      <span className="sk" style={{ width: 64, height: 16 }} />
                    </td>
                    <td>
                      <span className="sk" style={{ width: 92, height: 16 }} />
                    </td>
                    <td className="r">
                      <span className="sk" style={{ width: 24, height: 14 }} />
                    </td>
                    <td className="r">
                      <span className="sk" style={{ width: 24, height: 14 }} />
                    </td>
                    <td>
                      <span className="sk" style={{ width: 124, height: 14 }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : tasks.length === 0 ? (
        /* 空态充满(brx-fill:card 撑满 chrome-main 剩余高度,内容居中) */
        <div className="card card-fill">
          <ListChecks
            size={28}
            className="text-[var(--text-3)]"
            aria-hidden="true"
          />
          <p className="text-muted-foreground text-sm">暂无审查任务</p>
          <p className="text-muted-foreground" style={{ fontSize: 12 }}>
            上传招标与投标文件,创建第一个审查任务
          </p>
          <button type="button" className="btn btn-pri" onClick={openDialog}>
            <Plus className="ic" aria-hidden="true" />
            新建审查任务
          </button>
        </div>
      ) : (
        <div className="card">
          {/* 工具条(原型 s1):搜索(仅任务号,TaskOut 无项目名字段)+ 状态 seg */}
          <div className="toolbar">
            <input
              className="inp"
              style={{ width: 220 }}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索任务号…"
              aria-label="搜索任务号"
            />
            <div className="seg">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={cn(statusFilter === f.key && "on")}
                  onClick={() => setStatusFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          {filtered.length === 0 ? (
            <div className="tbl-foot">无匹配任务,调整搜索词或状态过滤</div>
          ) : (
            <>
              <div style={{ overflowX: "auto" }}>
                <table className="tbl">
                  <thead>
                    <tr>
                      {HEADERS.map((h, i) => (
                        <th
                          key={h}
                          scope="col"
                          className={cn(i >= 3 && i <= 4 && "r")}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((t) => {
                      const st = statusPill(t.status);
                      const mp = modePill(t.mode);
                      return (
                        <tr
                          key={t.id}
                          className="cursor-pointer"
                          onClick={() => router.push(workbenchHref(t.id))}
                        >
                          <td>
                            <Link
                              href={workbenchHref(t.id)}
                              className="mono"
                              title={t.id}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {t.id.slice(0, 8)}
                            </Link>
                          </td>
                          <td>
                            <span className={cn("pill", mp.cls)}>{mp.label}</span>
                          </td>
                          <td>
                            <span className={cn("pill", st.cls)}>
                              {st.dot ? (
                                <span className={cn("dot", st.dot)}></span>
                              ) : null}
                              {st.label}
                            </span>
                          </td>
                          {/* 行级计数:后端 GET /tasks 聚合计数直出;伪零门见 CountCell */}
                          <td className="r">
                            <CountCell task={t} field="fatal_unhandled" />
                          </td>
                          <td className="r">
                            <CountCell task={t} field="need_human_count" />
                          </td>
                          <td className="num">{formatDate(t.created_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="tbl-foot">
                共 {filtered.length}
                {filtered.length !== tasks.length
                  ? ` / ${tasks.length}`
                  : ""}{" "}
                个任务 · awaiting_confirm
                阶段不产生审查判定,问题数显示为 —(未进入审查 ≠ 通过)
              </div>
            </>
          )}
        </div>
      )}

      {/* ── note-bar(原型 s1;文案按 v1 真实口径)── */}
      <div className="note-bar">
        <Info className="ic" aria-hidden="true" />
        <span>
          快速评审上传后自动执行,无需基准确认;深度评审生成基线后进入「基准确认」卡点,基准未确认任务不会开始审查。
        </span>
      </div>

      {/* ── 新建审查任务(原型 s2:.overlay/.modal 三段结构;mode-card 单选 +
          招标/投标两组上传;文件必传——POST /tasks multipart 是后端唯一文档入口,
          零材料任务会被后端无条件直推空跑,Task 12 修复轮决定 (b))── */}
      {dialogOpen ? (
        <div
          className="overlay open"
          onClick={() => setDialogOpen(false)}
          role="presentation"
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="新建审查任务"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-hd">
              <h3>新建审查任务</h3>
              <button
                type="button"
                className="x"
                aria-label="关闭"
                onClick={() => setDialogOpen(false)}
              >
                <X className="ic" aria-hidden="true" />
              </button>
            </div>
            <div className="modal-bd">
              <div className="frm-row">
                <label>
                  评审模式<span className="must">*</span>
                </label>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 10,
                  }}
                >
                  {(["quick", "deep"] as const).map((m) => (
                    <label
                      key={m}
                      className={cn("mode-card", mode === m && "on")}
                    >
                      <input
                        type="radio"
                        name="br-review-mode"
                        value={m}
                        checked={mode === m}
                        onChange={() => setMode(m)}
                      />
                      <span>
                        <h4>{MODE_META[m].label}</h4>
                        <p>{MODE_META[m].desc}</p>
                      </span>
                    </label>
                  ))}
                </div>
                <div className="frm-help">{MODE_META[mode].hint}</div>
              </div>
              <FileGroup
                label="招标文件"
                files={tenderFiles}
                onAdd={(fs) => setTenderFiles((prev) => [...prev, ...fs])}
                onRemove={(i) =>
                  setTenderFiles((prev) => prev.filter((_, idx) => idx !== i))
                }
              />
              <FileGroup
                label="投标文件"
                files={bidFiles}
                onAdd={(fs) => setBidFiles((prev) => [...prev, ...fs])}
                onRemove={(i) =>
                  setBidFiles((prev) => prev.filter((_, idx) => idx !== i))
                }
              />
              <div className="note-bar">
                <Info className="ic" aria-hidden="true" />
                <span>
                  v1 后端将上传文件按 UTF-8 纯文本解码(.txt/.md
                  等文本格式最适配;PDF/Word 结构化解析后续版本支持)。
                </span>
              </div>
              {createMutation.isError ? (
                <div className="note-bar errbar" role="alert">
                  <Info className="ic" aria-hidden="true" />
                  <span>创建失败:{createMutation.error.message}</span>
                </div>
              ) : null}
            </div>
            <div className="modal-ft">
              <button
                type="button"
                className="btn btn-sec"
                onClick={() => setDialogOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn-pri"
                onClick={() =>
                  createMutation.mutate({
                    mode,
                    tender: tenderFiles,
                    bid: bidFiles,
                  })
                }
                disabled={
                  createMutation.isPending ||
                  tenderFiles.length === 0 ||
                  bidFiles.length === 0
                }
              >
                {createMutation.isPending ? "创建中…" : "创建任务"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
