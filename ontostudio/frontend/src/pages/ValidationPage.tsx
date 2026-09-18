/**
 * 07 校验中心骨架页（EAI-CUSTOM）：GB/T 48000.3 符合性五项 + SHACL 违规列表（静态示例）。
 * 真实数据面待 kernel P4（pyshacl 报告 + 国标符合性回归套件）。
 * seal（朱砂）语义：违规/失败；warning：警示。
 */
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";

const CHECKS = [
  { clause: "条款 5.4", title: "IRI 命名规约", note: "命名空间 + 本地标识符" },
  { clause: "条款 5.3", title: "序列化往返", note: "Turtle / JSON-LD 1.1" },
  { clause: "条款 5.3", title: "SHACL 报告", note: "约束验证结构化输出" },
  { clause: "附录 A", title: "元数据八项", note: "IRI/Name/Label/Definition…" },
  { clause: "条款 9", title: "扩展原则", note: "新域新命名空间 · 不改核心" },
];

const VIOLATIONS = [
  {
    level: "violation" as const,
    title: "约束类型取值越界",
    detail:
      'dg:constraintType 取值 "强制" 不在枚举 [强制性, 推荐性] 内 —— 来源：标书-2024-017 第 5.1 条抽取',
    meta: "shape: dg:StandardConstraintShape · focusNode: dg:id/9c21f7a0 · path: dg:constraintType",
  },
  {
    level: "warning" as const,
    title: "置信度低于推理门",
    detail:
      "实体「桑干河饮用水源保护区」置信度 0.62 < 0.70，暂不入推理空间；补充证据或人工确认后提升",
    meta: "shape: dg:ReasonableConfidenceShape · focusNode: dg:id/5d0a88 · path: dg:confidence · value: 0.62",
  },
];

export function ValidationPage() {
  return (
    <div className="p-6">
      <PageHeader
        clause="07 · 校验"
        title="校验中心"
        description="SHACL 闭世界校验管写路径 · OWL 开放世界管推理 · 国标符合性套件随构建运行"
        actions={
          <>
            <button className="border-border bg-card hover:bg-accent h-8 rounded-lg border px-3 text-xs font-medium shadow-xs">
              导出报告 JSON
            </button>
            <button className="bg-primary text-primary-foreground h-8 rounded-lg px-3 text-xs font-medium">
              重新校验
            </button>
          </>
        }
      />
      <Panel
        className="mb-3.5"
        title="GB/T 48000.3—2026 符合性"
        subtitle="v2026.09.18 · 构建 #412"
        actions={<Chip tone="primary">5 / 5 通过</Chip>}
      >
        <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-5">
          {CHECKS.map((check) => (
            <div
              key={check.title}
              className="border-border bg-background rounded-lg border p-3.5"
            >
              <div className="bg-primary/10 text-primary mb-2 grid h-7 w-7 place-items-center rounded-full text-sm font-bold">
                ✓
              </div>
              <div className="text-muted-foreground font-mono text-[10.5px]">{check.clause}</div>
              <b className="mt-0.5 block text-[13px]">{check.title}</b>
              <span className="text-muted-foreground text-[11.5px]">{check.note}</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel
        title="SHACL 违规"
        actions={<Chip tone="seal">2 项待处理</Chip>}
      >
        <div className="flex flex-col gap-2.5 p-4">
          <DemoTag className="self-end" />
          {VIOLATIONS.map((violation) => (
            <div
              key={violation.title}
              className="border-border bg-card flex gap-3 rounded-lg border p-3.5"
            >
              <span
                className={`w-1 flex-none rounded-sm ${violation.level === "violation" ? "bg-seal" : "bg-warning"}`}
              />
              <div className="min-w-0 flex-1">
                <h5 className="flex items-center gap-2 text-[13.5px] font-semibold">
                  {violation.title}
                  <Chip tone={violation.level === "violation" ? "seal" : "warning"}>
                    {violation.level}
                  </Chip>
                </h5>
                <p className="text-muted-foreground mt-0.5 text-xs">{violation.detail}</p>
                <div className="text-muted-foreground/80 mt-1.5 font-mono text-[11px] break-all">
                  {violation.meta}
                </div>
              </div>
              <button className="border-border bg-card hover:bg-accent h-7 flex-none self-start rounded-md border px-2.5 text-xs font-medium shadow-xs">
                去修复
              </button>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
