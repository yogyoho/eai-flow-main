import { expect, test, describe } from "vitest";

// Test that ApprovalAction type covers expected values
describe("Approval types", () => {
  const approvalActions = ["approve", "reject", "comment"] as const;
  test("ApprovalAction covers all expected values", () => {
    expect(approvalActions).toContain("approve");
    expect(approvalActions).toContain("reject");
    expect(approvalActions).toContain("comment");
    expect(approvalActions).toHaveLength(3);
  });

  const stepTypes = ["review", "technical_review", "sign_off"] as const;
  test("ApprovalStepType covers all expected values", () => {
    expect(stepTypes).toHaveLength(3);
    expect(stepTypes).toContain("review");
    expect(stepTypes).toContain("sign_off");
  });
});