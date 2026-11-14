import { describe, expect, it } from "@rstest/core";

import {
  ASSERTION_STATUS_LABELS,
  assembleGenerateKnobs,
  assertionWatermark,
  canLeaveIntake,
  gapStatusTone,
  materialEntityLabel,
  matrixStatusLabel,
  matrixStatusTone,
  matrixStrategyLabel,
  matrixSummary,
  projectSubtitle,
  projectTitle,
  sectionNames,
  sourcePathLabel,
  taskStatusView,
} from "@/extensions/bid-write/helpers";
import type {
  GapItem,
  MatrixRowOut,
  WriteTaskOut,
} from "@/extensions/bid-write/types";

function row(partial: Partial<MatrixRowOut>): MatrixRowOut {
  return {
    clause_id: "att:1",
    kind: "attachment",
    source_path: "tender.attachment_requirements",
    requirement: "营业执照",
    star: false,
    strategy: "full",
    target_section: "资格文件",
    evidence_refs: [],
    status: "draft",
    conf: 0.9,
    verified: false,
    note: "",
    ...partial,
  };
}

function task(partial: Partial<WriteTaskOut>): WriteTaskOut {
  return {
    id: "t0",
    biz_no: null,
    status: "matrix_ready",
    progress: {},
    error: null,
    project_name: null,
    lot_name: null,
    tender_no: null,
    created_at: null,
    engine_meta: {},
    ...partial,
  };
}

function gap(partial: Partial<GapItem>): GapItem {
  return {
    clause_id: "att:1",
    kind: "attachment",
    requirement: "营业执照",
    star: false,
    status: "draft",
    material_state: "无对应素材",
    evidence_refs: [],
    ...partial,
  };
}

describe("矩阵摘要", () => {
  it("按后端状态/星级/置信度聚合，不把未知值算入", () => {
    const summary = matrixSummary([
      row({ clause_id: "a", star: true, status: "blocked", conf: 0.42 }),
      row({ clause_id: "b", status: "confirmed", conf: 0.91 }),
      row({ clause_id: "c", status: "draft", conf: null }),
      row({ clause_id: "d", status: "draft", conf: 0.7, strategy: "pending" }),
    ]);
    expect(summary).toEqual({
      total: 4,
      star: 1,
      blocked: 1,
      confirmed: 1,
      strategyPending: 1,
      lowConfidence: 1,
    });
  });

  it("没有矩阵或仍有阻断时不能离开解析确认", () => {
    expect(canLeaveIntake(matrixSummary([]))).toBe(false);
    expect(canLeaveIntake(matrixSummary([row({ status: "blocked" })]))).toBe(
      false,
    );
    expect(canLeaveIntake(matrixSummary([row({ status: "confirmed" })]))).toBe(
      true,
    );
  });

  it("章节名去空去重，未知状态保留原值", () => {
    expect(
      sectionNames([
        row({ target_section: " 资格文件 " }),
        row({ target_section: "资格文件" }),
        row({ target_section: "" }),
        row({ target_section: "商务响应" }),
      ]),
    ).toEqual(["资格文件", "商务响应"]);

    expect(matrixStatusLabel("future")).toBe("future");
    expect(matrixStrategyLabel("future")).toBe("future");
    expect(sourcePathLabel("tender.unknown")).toBe("tender.unknown");
    expect(ASSERTION_STATUS_LABELS.SKIPPED).toBe("已跳过");
  });
});

describe("展示口径", () => {
  it("状态词表与 tone 对齐后端状态", () => {
    expect(taskStatusView(task({ status: "failed" }))).toMatchObject({
      label: "已失败",
      tone: "bad",
    });
    expect(matrixStatusTone(row({ status: "blocked" }))).toBe("bad");
    expect(matrixStatusTone(row({ status: "confirmed" }))).toBe("ok");
    expect(matrixStatusTone(row({ status: "draft" }))).toBe("gray");
  });

  it("缺口 tone 优先反映矩阵阻断，其次素材缺失", () => {
    expect(gapStatusTone(gap({ status: "confirmed" }))).toBe("ok");
    expect(gapStatusTone(gap({ status: "blocked" }))).toBe("bad");
    expect(gapStatusTone(gap({ material_state: "无对应素材" }))).toBe("bad");
    expect(gapStatusTone(gap({ material_state: "已匹配" }))).toBe("warn");
  });

  it("项目标题/副标题不使用演示值", () => {
    expect(projectTitle(task({ project_name: "   " }))).toBe("未命名写作项目");
    expect(projectTitle(task({ project_name: " 数据中心 " }))).toBe("数据中心");
    expect(projectSubtitle(task({}))).toBe("商务部分写作");
    expect(
      projectSubtitle(task({ lot_name: "标段一", tender_no: "T-1" })),
    ).toBe("标段一 · T-1");
  });

  it("断言门禁三态：未执行/阻断/无阻断", () => {
    expect(assertionWatermark(null)).toBe("unrun");
    expect(assertionWatermark({ blocked: true, pending: [{}] })).toBe(
      "blocked",
    );
    expect(assertionWatermark({ blocked: false, pending: [] })).toBe("clean");
  });
});

describe("生成旋钮装配(批廿五 P1-δ)", () => {
  const emptyDraft = {
    warrantyMonths: "",
    spareYears: "",
    responseHours: "",
    penaltyCap: "",
    signDate: "",
    priceNote: "",
    unitPrices: {},
  };

  it("全空草稿→空 body(后端 None 键不覆盖 meta.knobs)", () => {
    expect(assembleGenerateKnobs(emptyDraft)).toEqual({});
  });

  it("纯数字质保补单位,非数字原样透传", () => {
    expect(assembleGenerateKnobs({ ...emptyDraft, warrantyMonths: "24" })).toEqual({
      warranty_period: "24个月",
    });
    expect(
      assembleGenerateKnobs({ ...emptyDraft, warrantyMonths: "两年" }),
    ).toEqual({ warranty_period: "两年" });
  });

  it("备件/响应时限/违约金声明→通用承诺清单", () => {
    const knobs = assembleGenerateKnobs({
      ...emptyDraft,
      spareYears: "10",
      responseHours: "8",
      penaltyCap: "5",
    });
    expect(knobs.general_commitments).toEqual([
      { text: "备件供应年限:10年", clause_id: "" },
      { text: "故障响应时限:8小时", clause_id: "" },
      { text: "违约金上限:5%", clause_id: "" },
    ]);
  });

  it("空单价剔除,日期/备注非空才带", () => {
    const knobs = assembleGenerateKnobs({
      ...emptyDraft,
      unitPrices: { "1.1": "800000", "1.2": "  " },
      signDate: " 2026-11-20 ",
      priceNote: "暂估按最终结算",
    });
    expect(knobs.unit_prices).toEqual({ "1.1": "800000" });
    expect(knobs.sign_date).toBe("2026-11-20");
    expect(knobs.price_note).toBe("暂估按最终结算");
  });

  it("素材类型词表未知值原样展示", () => {
    expect(materialEntityLabel("qualification")).toBe("资质");
    expect(materialEntityLabel("future_type")).toBe("future_type");
  });
});
