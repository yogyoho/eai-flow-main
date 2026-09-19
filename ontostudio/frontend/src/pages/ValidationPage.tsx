/**
 * 07 校验中心（EAI-CUSTOM）——真实数据源：GET /ontology/formal/validate。
 * SHACL 报告（violations 五字段）+ 国标 GB/T 48000.3 五项符合性（kernel P4 套件）。
 * seal（朱砂）语义：违规/失败；warning：警示。
 */
import { useQuery } from "@tanstack/react-query";

import { ShieldCheck } from "lucide-react";

import { fetchFormalValidate, type ShaclViolation } from "@/api/formal-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";

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

  return (
    <div className="p-6">
      <PageHeader
        clause="07 · 校验"
        icon={ShieldCheck}
        title="校验中心"
        description="SHACL 闭世界校验管写路径 · OWL 开放世界管推理 · 国标符合性套件随构建运行"
        actions={
          <>
            <button
              className="border-border bg-card hover:bg-accent h-9 rounded-md border px-4 text-sm font-medium shadow-xs"
              onClick={() =>
                downloadReport({
                  shacl: data?.shacl,
                  conformance,
                })
              }
            >
              导出报告 JSON
            </button>
            <button
              className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium"
              onClick={() => validateQuery.refetch()}
            >
              {validateQuery.isFetching ? "校验中…" : "重新校验"}
            </button>
          </>
        }
      />
      {validateQuery.error ? (
        <div className="border-destructive/40 bg-destructive/10 text-destructive mb-3.5 rounded-lg border px-4 py-3 text-xs">
          校验服务不可达或未登录：{(validateQuery.error as Error).message}
        </div>
      ) : null}
      <Panel
        className="mb-3.5"
        title="GB/T 48000.3—2026 符合性"
        subtitle={data ? `${conformance.length} 项检查 · ${data.shacl.duration_ms}ms` : undefined}
        actions={
          <Chip tone={passedCount === conformance.length && conformance.length > 0 ? "primary" : "danger"}>
            {data ? `${passedCount} / ${conformance.length} 通过` : "加载中…"}
          </Chip>
        }
      >
        <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-5">
          {conformance.map((check) => (
            <div
              key={check.name}
              className="border-border bg-background rounded-lg border p-3.5"
            >
              <div
                className={`${check.passed ? "bg-primary/10 text-primary" : "bg-destructive/10 text-destructive"} mb-2 grid h-7 w-7 place-items-center rounded-full text-sm font-bold`}
              >
                {check.passed ? "✓" : "✕"}
              </div>
              <div className="text-muted-foreground font-mono text-[10.5px]">{check.clause}</div>
              <b className="mt-0.5 block text-[13px]">{check.name}</b>
              <span className="text-muted-foreground line-clamp-2 text-[11.5px]" title={check.detail}>
                {check.detail}
              </span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel
        title="SHACL 违规"
        actions={
          <Chip tone={violations.length > 0 ? "danger" : "primary"}>
            {data ? `${violations.length} 项待处理` : "…"}
          </Chip>
        }
      >
        <div className="flex flex-col gap-2.5 p-4">
          {violations.length === 0 && data ? (
            <div className="text-muted-foreground py-6 text-center text-xs">
              当前断言图无 SHACL 违规
            </div>
          ) : null}
          {violations.map((violation, index) => (
            <ViolationCard key={index} violation={violation} />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function ViolationCard({ violation }: { violation: ShaclViolation }) {
  const isWarning = (violation.severity ?? "").endsWith("Warning");
  return (
    <div className="border-border bg-card flex gap-3 rounded-lg border p-3.5">
      <span className={`w-1 flex-none rounded-sm ${isWarning ? "bg-warning" : "bg-destructive"}`} />
      <div className="min-w-0 flex-1">
        <h5 className="flex items-center gap-2 text-[13.5px] font-semibold">
          {violation.message ?? "约束违规"}
          <Chip tone={isWarning ? "warning" : "danger"}>
            {isWarning ? "warning" : "violation"}
          </Chip>
        </h5>
        <div className="text-muted-foreground/80 mt-1.5 font-mono text-[11px] break-all">
          {[
            violation.source,
            violation.focusNode ? `focusNode: ${violation.focusNode}` : null,
            violation.path ? `path: ${violation.path}` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </div>
      </div>
    </div>
  );
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
