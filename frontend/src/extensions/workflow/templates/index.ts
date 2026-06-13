import type { WorkflowGraph } from "../types";
import { SINGLE_REPORT_TEMPLATE } from "./single-report";
import { FOUR_PHASE_TEMPLATE } from "./four-phase";

export { SINGLE_REPORT_TEMPLATE, FOUR_PHASE_TEMPLATE };

export interface BuiltinTemplate {
  id: string;
  name: string;
  description: string;
  graph: WorkflowGraph;
}

export const BUILTIN_TEMPLATES: BuiltinTemplate[] = [
  { id: "single-report", name: "单一报告流程",
    description: "AI 写初稿 → 项目组修改 → 项目经理审核 → 部门负责人终审 → 驳回回退修改",
    graph: SINGLE_REPORT_TEMPLATE },
  { id: "four-phase", name: "四阶段管线",
    description: "可行性研究 → 初步设计 → 详细设计 → 实施交付，每阶段内含 AI 生成、修改、审核",
    graph: FOUR_PHASE_TEMPLATE },
];
