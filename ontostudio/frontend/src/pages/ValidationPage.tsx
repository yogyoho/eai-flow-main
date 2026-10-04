/**
 * 07 校验中心（EAI-CUSTOM, 2026-09-27 原型移植）——完全对照
 * docs/designs/ontostudio-frontend-redesign-20260926.html#validation：
 *
 * - 国标 C1-C5 五连小卡（顶部 tiles）；
 * - SHACL 违规 = 表格（级别/形状/目标/说明），hd 双徽章（错误/警告计数）；
 * - 校验运行面板（▶ 重新校验 + 上次运行耗时 + 注册表草稿校验指引 + 报告导出）。
 * 数据面：GET /formal/validate（SHACL 报告 + 国标 GB/T 48000.3 符合性套件）。
 * 口径（P0-5）：本套件只覆盖 §5.3 / §5.4 / 附录 A / 第 9 章，**不是**全文符合性——
 * 标题/副题不得声称「GB/T 48000.3 符合性」。判定口径见 docs/ontology/methodology.md §4.4。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  fetchFormalValidate,
  fetchOrphans,
  fetchValidateHistory,
  fetchValidateLast,
  purgeOrphans,
  type ShaclViolation,
} from "@/api/formal-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

/** SHACL focusNode → 实体 uuid（IRI 尾段；非实体 IRI 返回 null，不提供下钻）。 */
function uuidOf(iri: unknown): string | null {
  const m = String(iri ?? "").match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
  return m?.[1] ?? null;
}

export function ValidationPage() {
  // F9 同构：校验历史面板（每次「重新校验」自动记录于后端）
  const [historyOpen, setHistoryOpen] = useState(false);
  // 初始化 = 读路径（fetchValidateLast：上次完整结果原样还原，零 pyshacl）；
  // 校验运算是重操作（全图 pyshacl ~20s），只由「重新校验」按钮触发（2026-10-04 用户定案）
  const qc = useQueryClient();
  const validateQuery = useQuery({
    queryKey: ["formal", "validate"],
    queryFn: fetchValidateLast,
    staleTime: 30_000,
  });
  const revalidateMutation = useMutation({
    mutationFn: fetchFormalValidate,
    onSuccess: (result) => {
      qc.setQueryData(["formal", "validate"], { ...result, ranAt: new Date().toISOString() });
      void qc.invalidateQueries({ queryKey: ["formal", "validate-history"] });
    },
  });
  const ranAt = validateQuery.data?.ranAt ?? null;
  const historyQuery = useQuery({
    queryKey: ["formal", "validate-history"],
    queryFn: () => fetchValidateHistory(20),
    enabled: historyOpen,
    staleTime: 10_000,
  });
  // 内核孤儿治理：扫描(asserted 实体 vs dg_entities)→ 确认 → 精确清除
  const [orphanScan, setOrphanScan] = useState(false);
  const orphansQuery = useQuery({
    queryKey: ["formal", "orphans"],
    queryFn: fetchOrphans,
    enabled: orphanScan,
  });
  const [purging, setPurging] = useState(false);
  const [purgeMsg, setPurgeMsg] = useState<string | null>(null);
  const data = validateQuery.data;
  const conformance = data?.conformance ?? [];
  const passedCount = conformance.filter((check) => check.passed).length;
  const violations = data?.shacl.violations ?? [];
  // SHACL 违规分页（2026-10-04 用户反馈）：报告整包在内存, 客户端分页 50 条/页
  // （真实数据内核可产生千级违规, 全量渲染卡顿）; 新结果落缓存时回到第 1 页
  const [violPage, setViolPage] = useState(0);
  const VIOL_PAGE_SIZE = 50;
  useEffect(() => setViolPage(0), [violations]);
  const violTotalPages = Math.max(1, Math.ceil(violations.length / VIOL_PAGE_SIZE));
  const violPageRows = violations.slice(violPage * VIOL_PAGE_SIZE, violPage * VIOL_PAGE_SIZE + VIOL_PAGE_SIZE);
  const violPageWindow = useMemo(() => {
    const start = Math.max(0, Math.min(violPage - 2, violTotalPages - 5));
    return Array.from({ length: Math.min(5, violTotalPages) }, (_, i) => start + i);
  }, [violPage, violTotalPages]);
  const errorCount = violations.filter((v) => !(v.severity ?? "").endsWith("Warning")).length;
  const warningCount = violations.length - errorCount;

  return (
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1080px] p-6">
        <PageHeader
          icon={ShieldCheck}
          title="校验中心"
          description="SHACL 形状校验 + 国标 GB/T 48000 系符合性套件（C1-C5），每次全量装载/推理后可重跑。"
          actions={
            <span className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setOrphanScan((v) => !v)}
                className={cn(
                  "h-8 rounded-md border px-3 text-sm font-medium",
                  orphanScan
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border bg-card text-foreground hover:bg-muted",
                )}
              >
                数据治理
              </button>
              <button
                type="button"
                onClick={() => setHistoryOpen((v) => !v)}
                className={cn(
                  "h-8 rounded-md border px-3 text-sm font-medium",
                  historyOpen
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border bg-card text-foreground hover:bg-muted",
                )}
              >
                历史
              </button>
              <button
                type="button"
                className="border-border bg-card hover:bg-muted h-8 rounded-md border px-3 text-sm font-medium disabled:opacity-50"
                disabled={!data}
                onClick={() =>
                  downloadReport({
                    shacl: data?.shacl,
                    conformance,
                  })
                }
              >
                导出报告 JSON
              </button>
            </span>
          }
        />

        {/* 国标 C1-C5 五连小卡（V-A：detail 诊断接真——失败原因/通过摘要来自后端 CheckResult） */}
        <div className="grid grid-cols-2 gap-3.5 md:grid-cols-3 lg:grid-cols-5">
          {validateQuery.isLoading
            ? Array.from({ length: 5 }, (_, i) => (
                <div key={i} className="border-border bg-card rounded-xl border p-3.5 shadow-sm">
                  <div className="bg-muted h-3 w-24 animate-pulse rounded" />
                  <div className="bg-muted mt-2 h-6 w-8 animate-pulse rounded" />
                </div>
              ))
            : conformance.map((check) => (
                <div
                  key={check.name}
                  className={cn(
                    "rounded-xl border p-3.5 shadow-sm",
                    check.passed ? "border-border bg-card" : "border-destructive/40 bg-destructive/5",
                  )}
                  title={check.detail}
                >
                  <div className="text-muted-foreground truncate text-xs font-medium" title={`${check.clause} ${check.name}`}>
                    {check.clause} {check.name}
                  </div>
                  <div
                    className={cn(
                      "mt-1 text-2xl font-semibold",
                      check.passed ? "text-success" : "text-destructive",
                    )}
                  >
                    {check.passed ? "✓" : "✕"}
                  </div>
                  <div
                    className={cn(
                      "mt-1 text-xs font-medium",
                      check.passed ? "text-success" : "text-destructive",
                    )}
                  >
                    {check.passed ? "通过" : "未通过"}
                  </div>
                  <div
                    className={cn(
                      "mt-1 line-clamp-2 text-[11px] leading-tight",
                      check.passed ? "text-muted-foreground" : "text-destructive",
                    )}
                    title={check.detail}
                  >
                    {check.detail}
                  </div>
                </div>
              ))}
          {!validateQuery.isLoading && validateQuery.data === null ? (
            <div className="text-muted-foreground col-span-full py-6 text-center text-sm">
              尚未校验——点右上「重新校验」运行 SHACL 全图检查与国标五项。
            </div>
          ) : !validateQuery.isLoading && validateQuery.data && conformance.length === 0 ? (
            <div className="text-muted-foreground col-span-full py-6 text-center text-sm">
              国标符合性套件无检查项——请确认 registry 已装载。
            </div>
          ) : null}
        </div>
        <p className="text-muted-foreground mt-2 text-xs">
          C1-C5 为 <span className="font-medium">schema / 报告形态层</span>检查（registry 结构与序列化），
          与实例数据合规无关——实例层看下方 SHACL 违规表；需先全量装载。
        </p>

        {validateQuery.error ? (
          <div className="border-destructive/40 bg-destructive/10 text-destructive mt-3.5 rounded-lg border px-4 py-3 text-sm">
            校验服务不可达或未登录：{(validateQuery.error as Error).message}
          </div>
        ) : null}

        <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
          {/* SHACL 违规 = 表格（原型列：级别/形状/目标/说明） */}
          <Panel
            title="SHACL 违规"
            actions={
              <span className="flex items-center gap-1.5">
                <Chip tone={errorCount > 0 ? "danger" : "primary"}>{errorCount} 错误</Chip>
                <Chip tone={warningCount > 0 ? "warning" : "gray"}>{warningCount} 警告</Chip>
                <span className="text-muted-foreground/80 hidden font-mono text-xs lg:inline">
                  GET /formal/validate
                </span>
              </span>
            }
            className="overflow-hidden"
          >
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-border bg-muted/60 border-b">
                    {["级别", "形状", "目标", "说明"].map((head) => (
                      <th key={head} className="text-muted-foreground px-4 py-2 text-left text-xs font-medium">
                        {head}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {validateQuery.isLoading ? (
                    <tr>
                      <td colSpan={4} className="text-muted-foreground px-4 py-8 text-center text-sm">
                        <Loader /> 加载中…
                      </td>
                    </tr>
                  ) : data === null ? (
                    <tr>
                      <td colSpan={4} className="text-muted-foreground px-4 py-8 text-center text-sm">
                        尚未校验——点「重新校验」运行 SHACL 全图检查
                      </td>
                    </tr>
                  ) : violations.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="text-muted-foreground px-4 py-8 text-center text-sm">
                        当前断言图无 SHACL 违规
                      </td>
                    </tr>
                  ) : (
                    violPageRows.map((violation, index) => {
                      const isWarning = (violation.severity ?? "").endsWith("Warning");
                      return (
                        <tr key={index} className="border-border hover:bg-muted/50 border-b last:border-b-0">
                          <td className="px-4 py-2.5">
                            <Chip tone={isWarning ? "warning" : "danger"}>
                              {isWarning ? "警告" : "违规"}
                            </Chip>
                          </td>
                          <td className="px-4 py-2.5 font-mono text-xs">{violation.source ?? "—"}</td>
                          <td className="max-w-[12rem] truncate px-4 py-2.5 font-mono text-xs" title={violation.focusNode ?? undefined}>
                            {violation.focusNode ?? "—"}
                            {uuidOf(violation.focusNode) ? (
                              <button
                                type="button"
                                onClick={() => {
                                  window.location.hash = `entities:${uuidOf(violation.focusNode)}`;
                                }}
                                title="在实体库中打开该实体"
                                className="text-primary ml-1.5 hover:underline"
                              >
                                查看实体
                              </button>
                            ) : null}
                          </td>
                          <td className="max-w-[18rem] truncate px-4 py-2.5" title={violation.message ?? undefined}>
                            {violation.message ?? "—"}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            {violations.length > VIOL_PAGE_SIZE ? (
              <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-2.5 text-xs">
                <span className="text-muted-foreground">
                  共 <b className="text-foreground tabular-nums">{violations.length.toLocaleString()}</b> 条违规 · 第 {violPage + 1}/
                  {violTotalPages} 页
                </span>
                <div className="flex flex-wrap items-center gap-1">
                  <button
                    type="button"
                    disabled={violPage === 0}
                    onClick={() => setViolPage(0)}
                    className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 font-medium disabled:opacity-40"
                  >
                    首页
                  </button>
                  <button
                    type="button"
                    aria-label="上一页"
                    disabled={violPage === 0}
                    onClick={() => setViolPage((p) => Math.max(0, p - 1))}
                    className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 disabled:opacity-40"
                  >
                    ◀
                  </button>
                  {violPageWindow.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setViolPage(p)}
                      className={cn(
                        "rounded-md border px-2.5 py-1 font-medium tabular-nums",
                        p === violPage
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-card text-foreground hover:bg-muted",
                      )}
                    >
                      {p + 1}
                    </button>
                  ))}
                  <button
                    type="button"
                    aria-label="下一页"
                    disabled={violPage >= violTotalPages - 1}
                    onClick={() => setViolPage((p) => Math.min(violTotalPages - 1, p + 1))}
                    className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 disabled:opacity-40"
                  >
                    ▶
                  </button>
                  <button
                    type="button"
                    disabled={violPage >= violTotalPages - 1}
                    onClick={() => setViolPage(violTotalPages - 1)}
                    className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 font-medium disabled:opacity-40"
                  >
                    末页
                  </button>
                </div>
              </div>
            ) : null}
          </Panel>

          {/* 校验运行（原型） */}
          <Panel
            title="校验运行"
            actions={
              <span className="text-muted-foreground/80 hidden font-mono text-xs lg:inline">
                pyshacl 0.40 · shacl_graph 参数
              </span>
            }
          >
            <div className="flex flex-col gap-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => revalidateMutation.mutate()}
                  disabled={revalidateMutation.isPending}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  {revalidateMutation.isPending ? <LoaderInline /> : <Play className="h-3 w-3 fill-current" />}
                  重新校验
                </button>
                {revalidateMutation.isError ? (
                  <span className="text-destructive text-xs">校验失败：{(revalidateMutation.error as Error).message}</span>
                ) : null}
                <button
                  type="button"
                  disabled
                  title="按域过滤校验为规划项"
                  className="border-border bg-card rounded-md border px-3 py-1.5 text-sm opacity-60"
                >
                  范围：全域
                </button>
              </div>
              <p className="text-muted-foreground text-xs">
                上次运行{" "}
                {ranAt
                  ? new Date(ranAt).toLocaleString("zh-CN", { hour12: false })
                  : "—"}{" "}
                · {data ? `${data.shacl.duration_ms}ms` : "—"} · 国标五项 + SHACL shapes 编译一次性完成。
              </p>
              <div className="border-border flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                <span className="text-muted-foreground text-xs">
                  注册表草稿校验（建模器保存前）另行走 validate 端点。
                </span>
                <button
                  type="button"
                  onClick={() => {
                    window.location.hash = "modeler";
                  }}
                  className="text-primary text-xs font-medium underline-offset-2 hover:underline"
                >
                  去建模器校验草稿
                </button>
              </div>
            </div>
          </Panel>
        </div>

        {historyOpen ? (
          <div className="mt-3.5">
            <Panel title="校验历史" subtitle="近 20 次 SHACL 运行（每次「重新校验」自动记录）">
              {historyQuery.isLoading ? (
                <p className="text-muted-foreground p-4 text-sm">加载历史…</p>
              ) : (historyQuery.data?.history.length ?? 0) === 0 ? (
                <p className="text-muted-foreground p-4 text-sm">暂无历史——点「重新校验」后自动记录。</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="border-border bg-muted/50 border-b">
                        {["时间", "结论", "错误", "警告", "耗时"].map((head) => (
                          <th key={head} className="text-muted-foreground px-4 py-2 text-left text-xs font-medium">
                            {head}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-border divide-y">
                      {historyQuery.data!.history.map((h) => (
                        <tr key={h.ts} className="hover:bg-muted/50">
                          <td className="text-muted-foreground whitespace-nowrap px-4 py-2 text-xs">
                            {new Date(h.ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}
                          </td>
                          <td className="px-4 py-2">
                            <Chip tone={h.conforms ? "primary" : "warning"}>{h.conforms ? "通过" : "不通过"}</Chip>
                          </td>
                          <td className={cn("px-4 py-2 text-right tabular-nums", h.errors > 0 && "text-destructive")}>{h.errors}</td>
                          <td className={cn("px-4 py-2 text-right tabular-nums", h.warnings > 0 && "text-warning")}>{h.warnings}</td>
                          <td className="text-muted-foreground px-4 py-2 text-right tabular-nums">{h.duration_ms}ms</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>
        ) : null}

        {orphanScan ? (
          <div className="mt-3.5">
            <Panel title="内核孤儿治理" subtitle="断言图实体中 dg_entities 已无对应行——增量装载只增不删的残留">
              {orphansQuery.isLoading ? (
                <p className="text-muted-foreground p-4 text-sm">扫描断言图…</p>
              ) : orphansQuery.isError ? (
                <p className="text-destructive p-4 text-sm">扫描失败：{(orphansQuery.error as Error).message}</p>
              ) : (
                <div className="flex flex-col gap-2 p-4 text-sm">
                  <p className="text-muted-foreground text-xs">
                    断言图实体 {orphansQuery.data!.total_subjects.toLocaleString()} 个，其中孤儿{" "}
                    <b className={orphansQuery.data!.orphan_count > 0 ? "text-destructive" : "text-success"}>
                      {orphansQuery.data!.orphan_count}
                    </b>{" "}
                    个（无名 UUID、持续参与推理的残留数据）。
                  </p>
                  {orphansQuery.data!.orphan_count > 0 ? (
                    <>
                      <div className="bg-muted/60 max-h-40 overflow-y-auto rounded-md p-2 font-mono text-xs">
                        {orphansQuery.data!.orphans.slice(0, 20).map((iri) => (
                          <div key={iri} className="truncate">
                            {iri}
                          </div>
                        ))}
                        {orphansQuery.data!.orphan_count > 20 ? (
                          <div className="text-muted-foreground">… 其余 {orphansQuery.data!.orphan_count - 20} 条略</div>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        disabled={purging}
                        onClick={() => {
                          if (!window.confirm(`确认清除 ${orphansQuery.data!.orphan_count} 个孤儿实体的全部断言三元组？清除后建议全量重算刷新派生。`)) return;
                          setPurging(true);
                          purgeOrphans(orphansQuery.data!.orphans)
                            .then((r) => {
                              setPurgeMsg(`已清除 ${r.entities} 个实体 / ${r.removed_triples} 条三元组——建议到推理工作台全量重算刷新派生。`);
                              void orphansQuery.refetch();
                            })
                            .catch((e: Error) => setPurgeMsg(`清除失败：${e.message}`))
                            .finally(() => setPurging(false));
                        }}
                        className="border-destructive/40 text-destructive hover:bg-destructive/10 self-start rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                      >
                        {purging ? "清除中…" : `清除全部孤儿（${orphansQuery.data!.orphan_count}）`}
                      </button>
                    </>
                  ) : null}
                  {purgeMsg ? <p className="text-muted-foreground text-xs">{purgeMsg}</p> : null}
                </div>
              )}
            </Panel>
          </div>
        ) : null}

        <p className="text-muted-foreground mt-3.5 text-xs">
          本套件不覆盖 §6.2 核心实体类型、§7.3.2 表 1 的 34 条对象属性、§8.2 的 10 条公理规则。判定口径见
          docs/ontology/methodology.md §4.4。
        </p>
      </div>
    </div>
  );
}

function Loader() {
  return <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent align-middle" />;
}

function LoaderInline() {
  return <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent align-middle" />;
}

function downloadReport(payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ontostudio-validation-${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** 保留类型引用（ ViolationCard 由表格替代，字段契约见 formal-api）。 */
export type { ShaclViolation };
