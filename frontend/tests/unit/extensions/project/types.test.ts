import { expect, test, describe } from "vitest";

import {
  REPORT_TYPE_LABELS,
  PROJECT_STATUS_LABELS,
  CHAPTER_STATUS_LABELS,
  MILESTONE_STATUS_LABELS,
  MEMBER_ROLE_LABELS,
  STAGE_LABELS,
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

  test("PROJECT_STATUS_LABELS has all workflow statuses", () => {
    expect(PROJECT_STATUS_LABELS).toEqual({
      setup: "项目设定",
      outline: "大纲确认",
      writing: "AI撰写",
      editing: "协作编辑",
      approval: "审批",
      published: "已发布",
      archived: "已归档",
    });
  });

  test("CHAPTER_STATUS_LABELS has all chapter statuses", () => {
    expect(CHAPTER_STATUS_LABELS).toEqual({
      not_started: "未开始",
      pending: "待处理",
      writing: "AI撰写中",
      draft: "初稿",
      editing: "编辑中",
      pending_review: "待审核",
      completed: "已完成",
      rejected: "退回修改",
      approved: "已通过",
      signed: "已签发",
    });
  });

  test("MEMBER_ROLE_LABELS has all roles", () => {
    expect(MEMBER_ROLE_LABELS).toEqual({
      manager: "经理",
      editor: "编辑",
      writer: "撰写人",
      reviewer: "审核人",
      approver: "批准人",
    });
  });

  test("MILESTONE_STATUS_LABELS has all statuses", () => {
    expect(MILESTONE_STATUS_LABELS).toEqual({
      pending: "待开始",
      in_progress: "进行中",
      completed: "已完成",
      overdue: "已逾期",
    });
  });

  test("STAGE_LABELS has 6 stages", () => {
    expect(STAGE_LABELS).toHaveLength(6);
    expect(STAGE_LABELS[0]).toBe("项目设定");
    expect(STAGE_LABELS[5]).toBe("定稿输出");
  });
});
