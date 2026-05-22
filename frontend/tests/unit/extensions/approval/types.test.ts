import { expect, test, describe } from "vitest";

import type {
  ApprovalAction,
  ApprovalStepType,
  ApprovalWorkflow,
  ApprovalStep,
  ApprovalRecord,
} from "@/extensions/approval/types";

describe("Approval types", () => {
  test("ApprovalAction covers all expected values", () => {
    const actions: ApprovalAction[] = ["approve", "reject", "comment"];
    expect(actions).toContain("approve");
    expect(actions).toContain("reject");
    expect(actions).toContain("comment");
    expect(actions).toHaveLength(3);
  });

  test("ApprovalStepType covers all expected values", () => {
    const stepTypes: ApprovalStepType[] = ["review", "technical_review", "sign_off"];
    expect(stepTypes).toHaveLength(3);
    expect(stepTypes).toContain("review");
    expect(stepTypes).toContain("sign_off");
  });

  test("ApprovalWorkflow interface accepts valid object", () => {
    const workflow: ApprovalWorkflow = {
      id: "wf-1",
      name: "Environmental Review",
      reportType: "environmental_impact",
      steps: [],
      isDefault: false,
    };
    expect(workflow.id).toBe("wf-1");
    expect(workflow.name).toBe("Environmental Review");
    expect(workflow.steps).toEqual([]);
    expect(workflow.isDefault).toBe(false);
  });

  test("ApprovalStep interface accepts valid object", () => {
    const step: ApprovalStep = {
      id: "step-1",
      workflowId: "wf-1",
      order: 1,
      name: "Initial Review",
      requiredRole: "reviewer",
      canReject: true,
      parallel: false,
    };
    expect(step.id).toBe("step-1");
    expect(step.order).toBe(1);
    expect(step.canReject).toBe(true);
    expect(step.parallel).toBe(false);
  });

  test("ApprovalRecord interface accepts valid object", () => {
    const record: ApprovalRecord = {
      id: "rec-1",
      projectId: "proj-1",
      stepId: "step-1",
      chapterId: null,
      reviewerId: "user-1",
      reviewerName: "Alice",
      action: "approve",
      comment: "Looks good",
      actedAt: "2025-01-01T00:00:00Z",
    };
    expect(record.id).toBe("rec-1");
    expect(record.action).toBe("approve");
    expect(record.chapterId).toBeNull();
    expect(record.actedAt).toBe("2025-01-01T00:00:00Z");
  });
});
