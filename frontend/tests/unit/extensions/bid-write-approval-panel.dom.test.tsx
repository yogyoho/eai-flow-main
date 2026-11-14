// 批三十二：工作台审批面板（修订状态 / 审批人动作 / 批准后锁定）
import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { PropsWithChildren } from "react";

const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (
  path: string,
  init?: RequestInit,
) => Response | Promise<Response>;

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

import { ApprovalPanel } from "@/extensions/bid-write/components/ApprovalPanel";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const AST = {
  type: "doc",
  content: [{ type: "para", attrs: { slot_id: "s1" } }],
};

function state(
  revisionStatus: string,
  approvalStatus: string,
  canAct = false,
) {
  return {
    is_owner: true,
    revision: {
      id: "rev-1",
      revision_no: 1,
      status: revisionStatus,
      doc_hash: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
      schema_version: "0.1.0",
      assertion_snapshot: { status: "ok", summary: { d0: 0, d1: 1, d2: 0 } },
      approval_instance_id: "inst-1",
      hash_ok: true,
      created_at: "2026-11-14T10:00:00Z",
      submitted_at: "2026-11-14T10:00:00Z",
      decided_at: null,
    },
    approval: {
      instance_id: "inst-1",
      status: approvalStatus,
      current_node_id: "review-1",
      current_node_label: "商务负责人审批",
      gate_mode: "all",
      definition_id: null,
      workflow_source: "builtin",
      label: "商务投标正文审批",
      created_by: "u1",
      created_at: "2026-11-14T10:00:00Z",
      decided_at: null,
      can_act: canAct,
      my_review: canAct
        ? {
            id: "review-1",
            node_id: "review-1",
            reviewer_id: "u2",
            status: "pending",
            comment: null,
          }
        : null,
      reviews: [
        {
          id: "review-1",
          node_id: "review-1",
          node_label: "商务负责人审批",
          reviewer_id: "u2",
          reviewer_role: "reviewer",
          sequence: 1,
          status: canAct ? "pending" : approvalStatus === "approved" ? "approved" : "rejected",
          comment: null,
          created_at: "2026-11-14T10:00:00Z",
          updated_at: "2026-11-14T10:00:00Z",
        },
      ],
    },
    revisions: [],
  };
}

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  cleanup();
  calls.length = 0;
});

describe("ApprovalPanel", () => {
  it("被指派审批人可以批准并回写修订状态", async () => {
    let approved = false;
    responder = (path, init) => {
      if (path.endsWith("/approval/action")) {
        expect(init?.method).toBe("POST");
        approved = true;
        return jsonRes(state("approved", "approved"));
      }
      return jsonRes(
        approved
          ? state("approved", "approved")
          : state("submitted", "pending", true),
      );
    };
    const notices: string[] = [];
    const locks: boolean[] = [];
    render(
      <ApprovalPanel
        taskId="t1"
        ast={AST}
        cloudReady
        onNotice={(message) => notices.push(message)}
        onLockedChange={(locked) => locks.push(locked)}
      />,
      { wrapper },
    );

    expect(await screen.findByText("待你审批")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /批准/ }));
    await waitFor(() => expect(notices).toContain("审批已通过。"));
    const post = calls.find((call) => call.init?.method === "POST");
    expect(post?.path).toContain("/approval/action");
    expect(post?.init?.body as string).toContain('"action":"approved"');
    await waitFor(() => expect(locks.at(-1)).toBe(true));
  });

  it("驳回后显示重新提交入口，不锁定", async () => {
    responder = () => jsonRes(state("rejected", "rejected"));
    render(<ApprovalPanel taskId="t1" ast={AST} cloudReady />, { wrapper });
    expect(await screen.findByText("重新提交审批")).toBeTruthy();
    expect(screen.queryByText(/该修订已批准，正文锁定/)).toBeNull();
  });

  it("已批准修订显示锁定原因且不出现提交按钮", async () => {
    responder = () => jsonRes(state("approved", "approved"));
    render(<ApprovalPanel taskId="t1" ast={AST} cloudReady />, { wrapper });
    expect(await screen.findByText(/该修订已批准，正文锁定/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /提交审批/ })).toBeNull();
  });
});
