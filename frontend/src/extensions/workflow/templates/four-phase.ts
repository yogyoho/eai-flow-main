/** 四阶段管线 */
import type { WorkflowGraph } from "../types";

function makeSubTasks(sid: string, label: string): WorkflowGraph["subGraphs"][string] {
  return {
    nodes: [
      { id: `${sid}-ai`, type: "ai_generate", position: { x: 300, y: 50 }, data: { label: `AI 生成${label}报告`, aiAssist: true } },
      { id: `${sid}-edit`, type: "task", position: { x: 300, y: 150 }, data: { label: `修改${label}报告`, aiAssist: true } },
      { id: `${sid}-review`, type: "review", position: { x: 300, y: 250 }, data: { label: `${label}审核`, reviewMode: "all", reviewers: [{ type: "role", value: "reviewer", label: "审核人", required: true }], rollbackTarget: `${sid}-edit` } },
      { id: `${sid}-done`, type: "merge", position: { x: 300, y: 350 }, data: { label: `${label}阶段完成` } },
    ],
    edges: [
      { id: `e1-${sid}`, source: `${sid}-ai`, target: `${sid}-edit` },
      { id: `e2-${sid}`, source: `${sid}-edit`, target: `${sid}-review` },
      { id: `e3-${sid}`, source: `${sid}-review`, target: `${sid}-done`, label: "approved" },
      { id: `e4-${sid}`, source: `${sid}-review`, target: `${sid}-edit`, label: "rejected" },
    ],
  };
}

export const FOUR_PHASE_TEMPLATE: WorkflowGraph = {
  version: 2,
  mainGraph: {
    nodes: [
      { id: "sf-feas", type: "subflow", position: { x: 100, y: 200 }, data: { label: "可行性研究", team: "研究组", taskCount: 4 } },
      { id: "sf-prelim", type: "subflow", position: { x: 400, y: 200 }, data: { label: "初步设计", team: "设计组", taskCount: 4 } },
      { id: "sf-detail", type: "subflow", position: { x: 700, y: 200 }, data: { label: "详细设计", team: "设计组", taskCount: 4 } },
      { id: "sf-deliv", type: "subflow", position: { x: 1000, y: 200 }, data: { label: "实施交付", team: "项目组", taskCount: 4 } },
    ],
    edges: [
      { id: "e12", source: "sf-feas", target: "sf-prelim" },
      { id: "e23", source: "sf-prelim", target: "sf-detail" },
      { id: "e34", source: "sf-detail", target: "sf-deliv" },
    ],
  },
  subGraphs: {
    "sf-feas": makeSubTasks("sf-feas", "可行性研究"),
    "sf-prelim": makeSubTasks("sf-prelim", "初步设计"),
    "sf-detail": makeSubTasks("sf-detail", "详细设计"),
    "sf-deliv": makeSubTasks("sf-deliv", "实施交付"),
  },
};
