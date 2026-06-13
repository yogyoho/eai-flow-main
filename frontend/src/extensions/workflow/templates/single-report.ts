/** 单一报告流程 */
import type { WorkflowGraph } from "../types";

export const SINGLE_REPORT_TEMPLATE: WorkflowGraph = {
  version: 2,
  mainGraph: {
    nodes: [{
      id: "subflow-report", type: "subflow", position: { x: 400, y: 200 },
      data: { label: "报告编写与审核", team: "项目组", taskCount: 5 },
    }],
    edges: [],
  },
  subGraphs: {
    "subflow-report": {
      nodes: [
        { id: "t1", type: "ai_generate", position: { x: 400, y: 50 }, data: { label: "AI 自动编写初稿", aiAssist: true } },
        { id: "t2", type: "task", position: { x: 400, y: 150 }, data: { label: "项目组初稿修改", aiAssist: true } },
        { id: "t3", type: "review", position: { x: 400, y: 250 }, data: { label: "项目经理审核", reviewMode: "all", reviewers: [{ type: "role", value: "manager", label: "项目经理", required: true }], rollbackTarget: "t2" } },
        { id: "t4", type: "review", position: { x: 400, y: 350 }, data: { label: "部门负责人终审", reviewMode: "all", reviewers: [{ type: "position", value: "dept_head", label: "部门负责人", required: true }], rollbackTarget: "t2" } },
        { id: "t5", type: "merge", position: { x: 400, y: 450 }, data: { label: "报告提交归档" } },
      ],
      edges: [
        { id: "e1", source: "t1", target: "t2" },
        { id: "e2", source: "t2", target: "t3" },
        { id: "e3", source: "t3", target: "t4", label: "approved" },
        { id: "e4", source: "t3", target: "t2", label: "rejected" },
        { id: "e5", source: "t4", target: "t5", label: "approved" },
        { id: "e6", source: "t4", target: "t2", label: "rejected" },
      ],
    },
  },
};
