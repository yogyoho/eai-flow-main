import { expect, test, describe } from "vitest";

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

  test("PROJECT_STATUS_LABELS has simplified statuses", () => {
    expect(PROJECT_STATUS_LABELS).toEqual({
      active: "进行中",
      completed: "已完成",
      archived: "已归档",
    });
  });

  test("MEMBER_ROLE_LABELS has owner and member", () => {
    expect(MEMBER_ROLE_LABELS).toEqual({
      owner: "负责人",
      member: "成员",
    });
  });
});
