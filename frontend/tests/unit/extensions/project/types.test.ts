import { expect, test, describe } from "@rstest/core";

import {
  REPORT_TYPE_LABELS,
  PROJECT_STATUS_LABELS,
  MEMBER_ROLE_LABELS,
} from "@/extensions/project/types";

describe("Project type labels", () => {
  test("REPORT_TYPE_LABELS has all report types with Chinese labels", () => {
    expect(REPORT_TYPE_LABELS).toEqual({
      environmental_impact: "环境影响评价",
      geological_survey: "地质勘查",
      feasibility_study: "可行性研究",
      safety_assessment: "安全评价",
      energy_assessment: "节能评价",
      other: "其他",
    });
  });

  test("PROJECT_STATUS_LABELS has canonical statuses", () => {
    expect(PROJECT_STATUS_LABELS).toEqual({
      draft: "进行中",
      in_review: "审批中",
      approved: "已完成",
    });
  });

  test("MEMBER_ROLE_LABELS has canonical ProjectRoles", () => {
    expect(MEMBER_ROLE_LABELS).toEqual({
      owner: "负责人",
      phase_lead: "阶段负责人",
      writer: "撰写人",
      reviewer: "审核人",
      approver: "审批人",
    });
  });
});
