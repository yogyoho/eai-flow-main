import { expect, test, describe } from "vitest";

import {
  REPORT_TYPE_LABELS,
  PROJECT_STATUS_LABELS,
  CHAPTER_STATUS_LABELS,
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

  test("PROJECT_STATUS_LABELS has all statuses", () => {
    expect(PROJECT_STATUS_LABELS).toEqual({
      planning: "规划中",
      writing: "编写中",
      review: "审核中",
      finalizing: "定稿中",
      archived: "已归档",
    });
  });

  test("CHAPTER_STATUS_LABELS has all chapter statuses", () => {
    expect(CHAPTER_STATUS_LABELS).toEqual({
      not_started: "未开始",
      writing: "编写中",
      pending_review: "待审核",
      approved: "已通过",
      signed: "已签发",
    });
  });

  test("MEMBER_ROLE_LABELS has all roles", () => {
    expect(MEMBER_ROLE_LABELS).toEqual({
      manager: "项目经理",
      writer: "编写人",
      reviewer: "审核人",
      approver: "批准人",
      issuer: "签发人",
    });
  });
});