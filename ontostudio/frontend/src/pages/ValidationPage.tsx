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
import { useQuery } from "@tanstack/react-query";
import { Play, ShieldCheck } from "lucide-react";

import { fetchFormalValidate, type ShaclViolation } from "@/api/formal-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

export function ValidationPage() {
  const validateQuery = useQuery({
    queryKey: ["formal", "validate"],
    queryFn: fetchFormalValidate,
    staleTime: 30_000,
  });
  const data = validateQuery.data;
  const conformance = data?.conformance ?? [];
  const passedCount = conformance.filter((check) => check.passed).length;
  const violations = data?.shacl.violations ?? [];
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
          {!validateQuery.isLoading && validateQuery.data && conformance.length === 0 ? (
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
                  {!data ? (
                    <tr>
                      <td colSpan={4} className="text-muted-foreground px-4 py-8 text-center text-sm">
                        <Loader /> 加载中…
                      </td>
                    </tr>
                  ) : violations.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="text-muted-foreground px-4 py-8 text-center text-sm">
                        当前断言图无 SHACL 违规
                      </td>
                    </tr>
                  ) : (
                    violations.map((violation, index) => {
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
                  onClick={() => validateQuery.refetch()}
                  disabled={validateQuery.isFetching}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  {validateQuery.isFetching ? <LoaderInline /> : <Play className="h-3 w-3 fill-current" />}
                  重新校验
                </button>
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
                {validateQuery.dataUpdatedAt
                  ? new Date(validateQuery.dataUpdatedAt).toLocaleString("zh-CN", { hour12: false })
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
