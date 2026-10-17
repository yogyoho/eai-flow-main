/**
 * RAGFlow 连通状态徽标的态推导(纯函数,无 UI 依赖,单测于
 * tests/unit/extensions/contract-price/ragflow-phase.test.ts)。
 * EAI-CUSTOM: 供 SettingsView 页头徽标使用;`pending` 是组件级关注点
 * (状态查询进行中),不由 ragflowPhase() 返回。
 */

import type { RagflowStatusResponse } from "@/extensions/contract-price/types";

/** 两库固定名(与后端 ragflow_setup 常量一致)。 */
export const RAGFLOW_DATASETS = ["合同知识库", "合同货物分项表格"] as const;

export type RagflowPhase =
  | "pending"
  | "idle"
  | "initializing"
  | "ok"
  | "partial"
  | "err";

/** 态推导: 初始化 mutation 进行中 → initializing;available=false → err
 *  (RAGFlow 不可达——degraded 载荷可能不带 error 键,不能只看 error);
 *  两库全部 connected → ok;部分 connected → partial(「重新对齐」修复路径);
 *  error 键(或状态请求本身失败)→ err;其余(未创建/尚未拉到)→ idle。 */
export function ragflowPhase(
  status: { data?: RagflowStatusResponse; isError: boolean },
  initializing: boolean,
): RagflowPhase {
  if (initializing) return "initializing";
  const data = status.data;
  if (!data) return status.isError ? "err" : "idle";
  if (data.available === false) return "err";
  // datasets 缺失的防御(如仅带 error 的畸形载荷)按零连接处理
  const connected = (data.datasets ?? []).filter(
    (d) => d.status === "connected",
  ).length;
  if (connected === RAGFLOW_DATASETS.length) return "ok";
  if (connected > 0) return "partial";
  return data.error || status.isError ? "err" : "idle";
}
