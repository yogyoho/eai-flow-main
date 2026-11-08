import { afterEach, describe, expect, it } from "@rstest/core";
import { cleanup, render, screen } from "@testing-library/react";

// P1-β批五 T2(A-β5-⑥,规格 §5.7.2):GateMetricsRow 增 gate_status 四态 pill。
// 四态中文文案与后端 routers._GATE_TXT 逐字同源(fatal FAIL→NOT_SUBMITTABLE /
// fatal UNKNOWN→PENDING_HUMAN / major FAIL 或 L3 major INCONSISTENT→CONDITIONAL /
// else SUBMITTABLE);红 error(NOT_SUBMITTABLE+PENDING_HUMAN)/黄 warn(CONDITIONAL)/
// 绿 success(SUBMITTABLE)。gate_status 为 additive 可选键:旧 summary 形缺席时
// 既有格展示零改动、不渲染 pill、不炸(bug-4143 教训:异步查询文本须 await,
// 本件 pill 随 props 同步渲染,无异步面)。
import {
  GateMetricsRow,
  gateStatusPill,
} from "@/extensions/bid-review/components/primitives";

const METRICS = [
  { label: "致命", value: 1, tone: "error" as const },
  { label: "主要", value: 2, tone: "default" as const },
  { label: "次要", value: 0, tone: "success" as const },
  { label: "待人工", value: 3, tone: "default" as const },
];

describe("bid-review gateStatusPill 四态映射(批五 T2,后端 _GATE_TXT 同源)", () => {
  it("四态 tone/label 逐字同源:NOT_SUBMITTABLE+PENDING_HUMAN=error、CONDITIONAL=warn、SUBMITTABLE=success", () => {
    expect(gateStatusPill("NOT_SUBMITTABLE")).toEqual({
      tone: "error",
      label: "存在否决性风险,不建议提交。",
    });
    expect(gateStatusPill("PENDING_HUMAN")).toEqual({
      tone: "error",
      label: "关键项无法自动判定,必须人工确认。",
    });
    expect(gateStatusPill("CONDITIONAL")).toEqual({
      tone: "warn",
      label: "存在需整改项,建议整改后提交。",
    });
    expect(gateStatusPill("SUBMITTABLE")).toEqual({
      tone: "success",
      label: "未发现否决性风险,可按流程提交。",
    });
  });

  it("未知值 gray 兜底(不炸,回显原值)", () => {
    expect(gateStatusPill("SOMETHING_ELSE")).toEqual({
      tone: "gray",
      label: "SOMETHING_ELSE",
    });
  });
});

describe("bid-review GateMetricsRow gate_status 四态 pill 渲染(批五 T2)", () => {
  afterEach(() => {
    cleanup();
  });

  it("NOT_SUBMITTABLE → 渲染「不建议提交」pill;PENDING_HUMAN → 「必须人工确认」", () => {
    render(<GateMetricsRow metrics={METRICS} gateStatus="NOT_SUBMITTABLE" />);
    expect(screen.getByText(/不建议提交/)).toBeTruthy();
    expect(screen.getByText(/致命/)).toBeTruthy();
    cleanup();

    render(<GateMetricsRow metrics={METRICS} gateStatus="PENDING_HUMAN" />);
    expect(screen.getByText(/必须人工确认/)).toBeTruthy();
  });

  it("SUBMITTABLE → 渲染「可按流程提交」pill;CONDITIONAL → 「建议整改后提交」", () => {
    render(<GateMetricsRow metrics={METRICS} gateStatus="SUBMITTABLE" />);
    expect(screen.getByText(/可按流程提交/)).toBeTruthy();
    cleanup();

    render(<GateMetricsRow metrics={METRICS} gateStatus="CONDITIONAL" />);
    expect(screen.getByText(/建议整改后提交/)).toBeTruthy();
  });

  it("gate_status 缺席(旧 summary 形):不炸、既有格零回归、无 pill", () => {
    render(<GateMetricsRow metrics={METRICS} />);
    // 既有四格照常:标签/数值都在
    expect(screen.getByText("待人工")).toBeTruthy();
    expect(screen.getByText("致命")).toBeTruthy();
    // 四态文案零渲染(无 pill 壳)
    expect(screen.queryByText(/不建议提交/)).toBeNull();
    expect(screen.queryByText(/可按流程提交/)).toBeNull();
    expect(screen.queryByText(/必须人工确认/)).toBeNull();
    expect(screen.queryByText(/建议整改后提交/)).toBeNull();
  });
});
