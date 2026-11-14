"use client";

import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  ChevronRight,
  Info,
  RefreshCw,
  Sparkles,
  Undo2,
  Redo2,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  assertTaskDocument,
  getTaskDocument,
  putTaskDocument,
} from "@/extensions/bid-write/api";
import { ApprovalPanel } from "@/extensions/bid-write/components/ApprovalPanel";
import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import {
  type AssertRunner,
  type BidWriteEditorFlags,
  type BidWriteEditorHandle,
} from "@/extensions/bid-write/editor/BidWriteEditor";
import {
  editorLocalAssert,
  type AssertSummary,
  type ProvenanceHit,
} from "@/extensions/bid-write/editor/decor";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { astSections } from "@/extensions/bid-write/editor/outline";
import { type PasteNotice } from "@/extensions/bid-write/editor/paste";
import {
  AST_SCHEMA_VERSION,
  type AstJsonNode,
} from "@/extensions/bid-write/editor/schema.gen";
import {
  formatDate,
  formatPercent,
  matrixStatusLabel,
  matrixStatusTone,
  matrixStrategyLabel,
  matrixSummary,
  projectTitle,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useBidWriteMatrix,
  useSelectedWriteTask,
  useTaskMetrics,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";
import type { MatrixRowOut } from "@/extensions/bid-write/types";

// EAI-CUSTOM 批廿六 M0——PM 编辑器仅客户端挂载(prosemirror-view 不进 SSR 包)
const BidWriteEditor = dynamic(
  () =>
    import("@/extensions/bid-write/editor/BidWriteEditor").then(
      (mod) => mod.BidWriteEditor,
    ),
  {
    ssr: false,
    loading: () => <LoadingBlock label="正在挂载正文编辑器…" />,
  },
);

function normalizeHeading(text: string): string {
  return text
    .replace(/^[一二三四五六七八九十百]+、/, "")
    .replace(/\s+/g, "")
    .toLowerCase();
}

function rowsForHeading(rows: MatrixRowOut[], title: string): MatrixRowOut[] {
  const target = normalizeHeading(title);
  if (!target) return [];
  return rows.filter((row) => {
    const section = normalizeHeading(row.target_section);
    return (
      Boolean(section) &&
      (section === target ||
        section.includes(target) ||
        target.includes(section))
    );
  });
}

export function WorkbenchView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const matrix = useBidWriteMatrix(taskId);
  const gaps = useBidWriteGaps(taskId);
  const metrics = useTaskMetrics(taskId);
  const [activeSection, setActiveSection] = useState<string>("all");

  // 批廿六 M0——编辑器接线:演示文档 + 400ms 防抖回传;批廿八 M2——云端 AST
  // 加载(taskId 变化重取,ast 非空才重挂)/保存=PUT/断言侧信道/溯源跳转提示。
  const editorRef = useRef<BidWriteEditorHandle | null>(null);
  const [loadedAst, setLoadedAst] = useState<AstJsonNode | null>(null);
  const [docEpoch, setDocEpoch] = useState(0);
  const [docSource, setDocSource] = useState<"demo" | "cloud" | "cloud-error">(
    "demo",
  );
  const [saving, setSaving] = useState(false);
  const initialAst = useMemo(
    () => loadedAst ?? demoWorkbenchAst(),
    [loadedAst],
  );
  // 批三十:云端文档=后端真执行器(43 条断言);演示文档与任务数据无对应关系,
  // 继续用本地演示执行器并保留「演示文档」徽标,不把两套事实混在一起。
  const assertRunner = useMemo<AssertRunner>(() => {
    if (docSource === "cloud" && taskId) {
      return (ast) => assertTaskDocument(taskId, { ast });
    }
    return editorLocalAssert;
  }, [docSource, taskId]);
  const latestAstRef = useRef<AstJsonNode | null>(null);
  const [flags, setFlags] = useState<BidWriteEditorFlags>({
    canUndo: false,
    canRedo: false,
  });
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [currentAst, setCurrentAst] = useState<AstJsonNode | null>(null);
  const [approvalLocked, setApprovalLocked] = useState(false);

  // 云端文档加载:失败降级演示文档面(cloud-error 徽标),绝不空屏
  useEffect(() => {
    if (!taskId) return;
    let alive = true;
    getTaskDocument(taskId)
      .then((doc) => {
        if (!alive) return;
        if (doc.ast) {
          setLoadedAst(doc.ast);
          setCurrentAst(doc.ast);
          setDocSource("cloud");
          setDocEpoch((e) => e + 1); // key 重挂=服务端文档替换演示文档
        }
      })
      .catch(() => {
        if (alive) setDocSource("cloud-error");
      });
    return () => {
      alive = false;
    };
  }, [taskId]);

  // 断言状态栏(§六):SKIPPED 只进提示不算通过;runner 抛错=「校验未完成」
  const [assertSummary, setAssertSummary] = useState<AssertSummary | null>(
    null,
  );
  const [assertError, setAssertError] = useState(false);
  const handleAssert = useCallback((s: AssertSummary | null, err: boolean) => {
    setAssertSummary(s);
    setAssertError(err);
  }, []);

  // 溯源跳转提示(3s 消退,Timer 跨次复用)
  const [provJump, setProvJump] = useState<string | null>(null);
  const provTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleProvJump = useCallback((hit: ProvenanceHit) => {
    setProvJump(`溯源跳转:${hit.clause_id} → ${hit.anchor || "锚点未登记"}`);
    if (provTimer.current) clearTimeout(provTimer.current);
    provTimer.current = setTimeout(() => setProvJump(null), 3000);
  }, []);
  useEffect(
    () => () => {
      if (provTimer.current) clearTimeout(provTimer.current);
    },
    [],
  );

  // 批廿七 M1——违规即时提示(3s 自动消退);Timer 跨次复用,卸载清算
  const [violation, setViolation] = useState<string | null>(null);
  const violationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (violationTimer.current) clearTimeout(violationTimer.current);
    },
    [],
  );
  const handleViolation = useCallback((v: { message: string }) => {
    setViolation(v.message);
    if (violationTimer.current) clearTimeout(violationTimer.current);
    violationTimer.current = setTimeout(() => setViolation(null), 3000);
  }, []);

  // 批三十一 M5——粘贴清洗提示(3s 消退):成功提示剥离格式,拒绝提示改分段/目标结构
  const [pasteNotice, setPasteNotice] = useState<string | null>(null);
  const pasteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (pasteTimer.current) clearTimeout(pasteTimer.current);
    },
    [],
  );
  const handlePasteSanitized = useCallback((notice: PasteNotice) => {
    let message: string;
    if (notice.rejected === "cross_block") {
      message = "跨段粘贴已拦截：请分段粘贴，避免替换章节结构。";
    } else if (notice.rejected === "unsupported") {
      message = "当前结构不支持直接粘贴：请粘贴到正文段落或表格文本格。";
    } else if (notice.rejected === "empty") {
      message = "剪贴板没有可粘贴文本。";
    } else {
      const format = notice.markupStripped ? "已去除外部格式，" : "";
      message = `已按纯文本粘贴 ${notice.lines} 段（${format}不写入外部标签/样式）。`;
    }
    setPasteNotice(message);
    if (pasteTimer.current) clearTimeout(pasteTimer.current);
    pasteTimer.current = setTimeout(() => setPasteNotice(null), 3000);
  }, []);

  // 批三十二——审批提示（3s 消退）；批准后锁定编辑器
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null);
  const approvalTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (approvalTimer.current) clearTimeout(approvalTimer.current);
    },
    [],
  );
  const handleApprovalNotice = useCallback((message: string) => {
    setApprovalNotice(message);
    if (approvalTimer.current) clearTimeout(approvalTimer.current);
    approvalTimer.current = setTimeout(() => setApprovalNotice(null), 4000);
  }, []);
  const handleApprovalLocked = useCallback((locked: boolean) => {
    setApprovalLocked(locked);
  }, []);

  const handleDocChange = useCallback(
    (ast: AstJsonNode, f: BidWriteEditorFlags) => {
      latestAstRef.current = ast;
      setCurrentAst(ast);
      setFlags(f);
    },
    [],
  );
  const handleSave = useCallback(async () => {
    const editor = editorRef.current;
    // 防御:动态编辑器尚未挂载/测试替身无命令面时,退回最近一次回传的 AST。
    const ast =
      (editor && typeof editor.serializeNow === "function"
        ? editor.serializeNow()
        : null) ?? latestAstRef.current;
    if (!ast || !taskId || saving) return;
    latestAstRef.current = ast;
    setSaving(true);
    try {
      const doc = await putTaskDocument(taskId, {
        ast,
        schema_version: AST_SCHEMA_VERSION,
      });
      setCurrentAst(ast);
      setDocSource("cloud");
      setSavedAt(
        doc.updated_at
          ? new Date(doc.updated_at).toLocaleTimeString("zh-CN", {
              hour12: false,
            })
          : new Date().toLocaleTimeString("zh-CN", { hour12: false }),
      );
    } catch (e) {
      setViolation(e instanceof ApiError ? e.message : "保存失败,请重试");
      if (violationTimer.current) clearTimeout(violationTimer.current);
      violationTimer.current = setTimeout(() => setViolation(null), 3000);
    } finally {
      setSaving(false);
    }
  }, [taskId, saving]);

  const rows = useMemo(() => matrix.data?.items ?? [], [matrix.data?.items]);
  const summary = useMemo(() => matrixSummary(rows), [rows]);
  const m = metrics.data?.metrics ?? null;

  const docSections = useMemo(() => astSections(initialAst), [initialAst]);
  const activeDocSection = useMemo(
    () => docSections.find((section) => section.key === activeSection) ?? null,
    [activeSection, docSections],
  );

  useEffect(() => {
    if (
      activeSection !== "all" &&
      !docSections.some((section) => section.key === activeSection)
    ) {
      setActiveSection("all");
    }
  }, [activeSection, docSections]);

  const matchedRows = useMemo(
    () =>
      activeDocSection ? rowsForHeading(rows, activeDocSection.title) : rows,
    [activeDocSection, rows],
  );
  const visibleRows = matchedRows.length > 0 ? matchedRows : rows;

  const activateSection = (key: string) => {
    setActiveSection(key);
    requestAnimationFrame(() => {
      const editor = editorRef.current;
      if (!editor || typeof editor.scrollToSection !== "function") return;
      if (!editor.scrollToSection(key)) {
        handleViolation({ message: "正文中未找到该章节，已保留当前视图。" });
      }
    });
  };

  const gapItems = gaps.data?.items ?? [];
  const noMaterial = gapItems.filter(
    (item) => item.material_state === "无对应素材",
  );
  const assertions = gaps.data?.assertions ?? null;

  return (
    <>
      <PageHead
        icon={BookOpen}
        title="④ 写作工作台"
        subtitle={
          task
            ? `${projectTitle(task)} · 矩阵/缺口/预审查/埋点实读；正文编辑器 M6（审批修订+真执行器+负偏离展开+粘贴清洗）`
            : "矩阵/缺口/预审查/埋点实读；正文编辑器 M6（审批修订+真执行器+负偏离展开+粘贴清洗）"
        }
        actions={
          <>
            <Link
              href={
                taskId ? writeTaskHref("review", taskId) : "/bid-write/review"
              }
              className="btn btn-sm"
            >
              预审查
            </Link>
            <Link
              href={
                taskId
                  ? writeTaskHref("generate", taskId)
                  : "/bid-write/generate"
              }
              className="btn pri btn-sm"
            >
              生成配置
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          </>
        }
      />

      {isLoading ? (
        <LoadingBlock label="正在加载工作台…" />
      ) : !task ? (
        <EmptyState
          icon={BookOpen}
          title="还没有写作项目"
          description="先创建项目并完成响应矩阵确认，再进入工作台。"
          action={
            <Link href="/bid-write" className="btn pri">
              去项目列表
            </Link>
          }
        />
      ) : matrix.isLoading ? (
        <LoadingBlock label="正在加载响应矩阵…" />
      ) : matrix.error ? (
        <ErrorBlock
          error={matrix.error}
          onRetry={() => void matrix.refetch()}
        />
      ) : (
        <>
          {summary.blocked > 0 ? (
            <div className="banner bad">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                <b>{summary.blocked} 条低置信行未确认：</b>
                生成前必须回到解析确认清零阻断，否则断言与导出门禁会拦截。
              </span>
            </div>
          ) : (
            <div className="banner info">
              <Info size={15} aria-hidden="true" />
              <span>
                正文编辑器 M6
                已接入：审批修订冻结/会签或签/批准锁定、编辑/撤销、AST
                云端存储、负偏离展开面
                （自愈维护）、富文本粘贴清洗（外部标签/样式不落
                AST）与后端真执行器 （43 条断言按锚点回写）可用；演示文档
                使用本地演示执行器，校验不可用时显示「校验未完成」。
              </span>
            </div>
          )}

          <div className="wb bw-mt">
            <aside className="card bw-outline">
              <div className="card-h">
                <h3>文档结构</h3>
                <span className="r">
                  <Badge tone="gray">{docSections.length} 节</Badge>
                </span>
              </div>
              <div className="card-b">
                <button
                  type="button"
                  className={`outline-item ${activeSection === "all" ? "on" : ""}`}
                  onClick={() => activateSection("all")}
                >
                  <span className="oi-t">全部正文</span>
                  <span className="cnt">{rows.length}</span>
                </button>
                {docSections.map((section) => {
                  const sectionRows = rowsForHeading(rows, section.title);
                  const blocked = sectionRows.filter(
                    (row) => row.status === "blocked",
                  ).length;
                  return (
                    <button
                      key={section.key}
                      type="button"
                      className={`outline-item ${activeSection === section.key ? "on" : ""}`}
                      onClick={() => activateSection(section.key)}
                    >
                      <span className="oi-t">{section.title}</span>
                      {blocked > 0 ? (
                        <span
                          className="oi-blocked"
                          title={`${blocked} 条阻断`}
                        >
                          {blocked}
                        </span>
                      ) : null}
                      {sectionRows.length > 0 ? (
                        <span className="cnt">{sectionRows.length}</span>
                      ) : null}
                    </button>
                  );
                })}
                {docSections.length === 0 ? (
                  <p className="bw-muted bw-pad-sm">
                    正文还没有章节。请先在生成配置中生成正文，或保存一份包含
                    section 节点的云端文档。
                  </p>
                ) : null}
              </div>
              <div className="bw-outline-foot">
                {m ? (
                  <>
                    <span>
                      最近生成 <b>{formatDate(metrics.data?.run_at ?? null)}</b>
                    </span>
                    <Badge tone={m.d0_count === 0 ? "ok" : "warn"}>
                      D0 {m.d0_count} · 通过率{" "}
                      {formatPercent(m.assertion_pass_rate)}
                    </Badge>
                  </>
                ) : (
                  <>
                    <span>正文</span>
                    <Badge tone="gray">未生成</Badge>
                  </>
                )}
              </div>
            </aside>

            <section className="card bw-doc">
              <div className="card-h">
                <h3>{activeDocSection?.title ?? "全部正文"}</h3>
                <span className="r">
                  <Badge
                    tone={
                      docSource === "cloud"
                        ? "ok"
                        : docSource === "cloud-error"
                          ? "warn"
                          : "gray"
                    }
                  >
                    {docSource === "cloud"
                      ? "云端文档"
                      : docSource === "cloud-error"
                        ? "云端加载失败(演示文档)"
                        : "演示文档"}
                  </Badge>
                  <Badge tone={summary.blocked > 0 ? "bad" : "ok"} dot>
                    {summary.blocked > 0
                      ? `${summary.blocked} 项阻断`
                      : "矩阵无阻断"}
                  </Badge>
                </span>
              </div>
              <ApprovalPanel
                taskId={taskId}
                ast={currentAst ?? initialAst}
                cloudReady={docSource === "cloud"}
                onLockedChange={handleApprovalLocked}
                onNotice={handleApprovalNotice}
              />
              <div className="ed-toolbar">
                <button
                  type="button"
                  disabled={!flags.canUndo || approvalLocked}
                  title="撤销（Ctrl+Z）"
                  onClick={() => editorRef.current?.undo()}
                >
                  <Undo2 size={14} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  disabled={!flags.canRedo || approvalLocked}
                  title="重做（Ctrl+Y）"
                  onClick={() => editorRef.current?.redo()}
                >
                  <Redo2 size={14} aria-hidden="true" />
                </button>
                <span className="sep" />
                <button
                  type="button"
                  disabled={saving || approvalLocked}
                  title={
                    approvalLocked
                      ? "正文已批准并锁定；修改需从新修订流程重开"
                      : "保存=写入云端 AST 存储(PUT /tasks/{id}/document)"
                  }
                  onClick={() => void handleSave()}
                >
                  {saving ? "保存中…" : "保存"}
                </button>
                <button type="button" disabled title="重审接口尚未接入">
                  <RefreshCw size={14} aria-hidden="true" />
                  重审受影响断言
                </button>
                <span className="ed-spacer" />
                <button
                  type="button"
                  disabled
                  title="AI 建议需要生成正文与断言快照"
                >
                  <Sparkles size={14} aria-hidden="true" />
                  查看 AI 建议
                </button>
              </div>
              {violation ? (
                <div className="ed-notice" role="status">
                  {violation}
                </div>
              ) : null}
              {provJump ? (
                <div className="ed-notice" role="status">
                  {provJump}
                </div>
              ) : null}
              {pasteNotice ? (
                <div className="ed-notice" role="status">
                  {pasteNotice}
                </div>
              ) : null}
              {approvalNotice ? (
                <div className="ed-notice" role="status">
                  {approvalNotice}
                </div>
              ) : null}
              <div className="doc-body">
                <BidWriteEditor
                  key={docEpoch}
                  ref={editorRef}
                  initialAst={initialAst}
                  onDocChange={handleDocChange}
                  onViolation={handleViolation}
                  assertRunner={assertRunner}
                  onAssert={handleAssert}
                  onProvenanceJump={handleProvJump}
                  onPasteSanitized={handlePasteSanitized}
                  readOnly={approvalLocked}
                  ariaLabel={
                    docSource === "cloud"
                      ? "投标正文编辑器（云端文档）"
                      : "投标正文编辑器（演示文档）"
                  }
                />
                <p className="bw-muted bw-mt-sm">
                  M6：审批修订已接入——提交时冻结
                  AST/hash/断言快照，审批只审冻结修订；
                  批准后正文锁定，驳回后可继续编辑并重新提交。M5：富文本粘贴清洗已接入——Word/网页内容只保留可见文本，外部标签、
                  样式、脚本与隐藏内容不进入
                  AST；锁定段/金额/来源列/枚举的粘贴仍被 M1
                  约束拦截。M4：负偏离展开面已接入——响应策略选「负偏离」自动展开偏离说明
                  （偏离原因+替代方案），未闭环 D0、孤儿展开面 D1（SK-RT-005，与
                  后端同口径）；M1 锁定段/金额/来源列只读、下拉、缺件占位禁删、
                  M2 断言联动与 AST
                  存储均生效；云端文档的断言由后端真执行器产出，
                  演示文档使用本地演示执行器；SKIPPED 只提示不算通过，校验未完成
                  时导出判定以预审查为准。
                </p>

                <div className="bw-doc-sub">
                  <b>响应矩阵底稿</b>
                  <span>
                    {visibleRows.length} 条要求
                    {activeDocSection && matchedRows.length === 0
                      ? "（该章节未绑定矩阵行，显示全部）"
                      : ""}
                  </span>
                </div>
                {visibleRows.length === 0 ? (
                  <p className="bw-muted">当前章节没有矩阵行。</p>
                ) : (
                  <div className="tbl-wrap">
                    <table className="tbl dense">
                      <thead>
                        <tr>
                          <th>条款</th>
                          <th>要求摘录</th>
                          <th>策略</th>
                          <th>状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleRows.map((row) => (
                          <tr key={row.clause_id}>
                            <td className="mono bw-nowrap">{row.clause_id}</td>
                            <td>
                              <span
                                className="excerpt ellipsis"
                                title={row.requirement}
                              >
                                {row.requirement
                                  ? row.requirement
                                  : "（空要求）"}
                              </span>
                            </td>
                            <td className="bw-nowrap">
                              {matrixStrategyLabel(row.strategy)}
                              {row.star ? (
                                <span className="star"> ★</span>
                              ) : null}
                            </td>
                            <td>
                              <Badge tone={matrixStatusTone(row)} dot>
                                {matrixStatusLabel(row.status)}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>

            <aside className="bw-side">
              <div className="card">
                <div className="card-h">
                  <h3>素材缺口</h3>
                  <span className="r">
                    <Badge tone={noMaterial.length > 0 ? "bad" : "ok"}>
                      {noMaterial.length} / {gapItems.length}
                    </Badge>
                  </span>
                </div>
                <div className="card-b">
                  {gaps.isLoading ? (
                    <LoadingBlock label="加载素材缺口…" />
                  ) : noMaterial.length === 0 ? (
                    <p className="bw-muted">没有待补素材。</p>
                  ) : (
                    <ul className="bw-side-list">
                      {noMaterial.slice(0, 8).map((item) => (
                        <li key={item.clause_id}>
                          <span className="mono">{item.clause_id}</span>
                          <span title={item.requirement}>
                            {item.requirement}
                          </span>
                          {item.star ? <span className="star">★</span> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                  {noMaterial.length > 8 ? (
                    <p className="bw-muted bw-mt-sm">
                      另有 {noMaterial.length - 8} 条缺口…
                    </p>
                  ) : null}
                  <Link
                    href={
                      taskId
                        ? writeTaskHref("materials", taskId)
                        : "/bid-write/materials"
                    }
                    className="btn btn-sm soft bw-full"
                  >
                    查看全部缺口
                  </Link>
                </div>
              </div>

              <div className="card bw-mt">
                <div className="card-h">
                  <h3>预审查</h3>
                  <span className="r">
                    {assertions ? (
                      <Badge tone={assertions.blocked ? "bad" : "ok"} dot>
                        {assertions.blocked ? "阻断" : "通过"}
                      </Badge>
                    ) : (
                      <Badge tone="gray">未执行</Badge>
                    )}
                  </span>
                </div>
                <div className="card-b">
                  {assertions ? (
                    <>
                      <div className="bw-inline-facts bw-facts-col">
                        <span>
                          执行时间 <b>{formatDate(assertions.run_at)}</b>
                        </span>
                        <span>
                          待补 <b>{assertions.pending.length}</b> · 跳过{" "}
                          <b>{assertions.skipped.length}</b>
                        </span>
                      </div>
                      {assertions.pending.slice(0, 4).map((item) => (
                        <div className="bw-mini-item" key={item.assertion_id}>
                          <span className="mono">{item.assertion_id}</span>
                          <span>{item.message}</span>
                        </div>
                      ))}
                      {assertions.pending.length > 4 ? (
                        <p className="bw-muted">
                          另有 {assertions.pending.length - 4} 条待补…
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <p className="bw-muted">
                      尚未执行断言。导出门禁在执行后才会给出明确判定。
                    </p>
                  )}
                  <Link
                    href={
                      taskId
                        ? writeTaskHref("review", taskId)
                        : "/bid-write/review"
                    }
                    className="btn btn-sm soft bw-full"
                  >
                    查看预审查
                  </Link>
                </div>
              </div>
            </aside>
          </div>

          <div className="statusbar">
            <span className="dot-ok" />
            <span>
              矩阵 {summary.total} 行 · 已确认 {summary.confirmed} · 阻断{" "}
              {summary.blocked}
            </span>
            <span className="sep" />
            <span>素材缺口 {noMaterial.length}</span>
            <span className="sep" />
            <span>
              预审查{" "}
              {assertions ? (assertions.blocked ? "阻断" : "可导出") : "未执行"}
            </span>
            <span className="sep" />
            {assertError ? (
              <span title="断言服务不可用——导出判定以预审查为准,不默认放行">
                校验未完成
              </span>
            ) : assertSummary ? (
              <span
                title={assertSummary.skipped
                  .map((s) => `${s.code}:${s.reason ?? ""}`)
                  .join(";")}
              >
                校验 D0 {assertSummary.d0} · D1 {assertSummary.d1} · D2{" "}
                {assertSummary.d2}
                {assertSummary.skipped.length > 0
                  ? ` · 因 ${assertSummary.skipped.map((s) => s.code).join("/")} 跳过 ${assertSummary.skipped.reduce((a, b) => a + b.count, 0)}(不算通过)`
                  : ""}
              </span>
            ) : (
              <span>校验待运行</span>
            )}
            <span className="sep" />
            <span>保存 {savedAt ?? "未保存"}</span>
            {m ? (
              <>
                <span className="sep" />
                <span>
                  人工编辑占比 {formatPercent(m.manual_edit_ratio)} · 耗时{" "}
                  {(m.latency_ms / 1000).toFixed(1)}s
                </span>
              </>
            ) : null}
            <span className="grow" />
            {taskId ? (
              <Link
                href={writeTaskHref("export", taskId)}
                className="bw-inline-link"
              >
                去导出
                <ChevronRight size={12} aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        </>
      )}
    </>
  );
}
